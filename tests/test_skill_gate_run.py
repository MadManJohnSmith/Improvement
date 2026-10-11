"""E3: the corpus runs against a real mode, or says precisely that it cannot.

Until this existed the gate could score observations that nothing produced. The
runner's job is narrow and the cases pin it: it must never invent a verdict, a
case it could not run has to come back `NOT_COVERED` rather than as a pass, and
the evaluator prompt must not carry the expected answer -- a case that travels
with its own solution measures reading, and the gate would happily certify it.

The dispatch is injected, so these run without a session; a session is the
operator's, and the no-session path is covered separately with the real
acquisition code.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus_compiler
import skill_gate_run

LIBRARY = ROOT / "library"
CAND_DIGEST = "a" * 64


class _FixtureEvaluator(skill_gate_run.CompatibleEvaluator):
    """Only a test adapter: proves the fixture's routing and actual case cwd.

    This is not a claim that DSH operational modes can load library skills. A
    production adapter must inspect their effective publication and layout.
    """
    def prepare(self, client, corpus, mode, root):
        self.root = root
        return {case["case_id"]: mode for case in corpus["cases"]}

    def verify_case(self, client, case, preset, path):
        return (path.parent == self.root and path.is_dir()
                and not path.is_symlink()
                and case["target_skill"] in client.effective_skills
                and preset in [row["id"] for row in client.roster])


class _FakeClient:
    """Stands in for the DSH client: records what it was asked, answers by case.

    The surface is the session API DSH 0.2.0-rc.2 really serves, not an
    ``evaluator`` RPC this release never had. A fixture shaped like the endpoint
    that does not exist would let the runner pass against a contract no
    runtime honours, which is exactly the defect this regression guards.

    Two halves of it are deliberately strict, because the lax versions are what
    let the defects this file guards stand:

    * it serves the *authorized* preset API (`agentPresets/list` +
      `agentPresets/read`) with the exact operational composition, so the mode
      the runner dispatches is one it verified rather than one it invented;
    * it answers the way the prompt asks -- by *persisting* ``result.json``
      into the case workspace -- instead of speaking its verdict in prose. A
      fixture that answered in assistant text would certify the very fallback
      this regression removes.
    """

    # The exact composition the published bundle declares: the six operational
    # DSH plugins plus the anti-escalation guard, which resolves to a path.
    GOOD_COMPOSITION = """- id: persona
  name: '@deepseek-ai/dsh-persona'
- id: bash
  name: '@deepseek-ai/dsh-tool-bash'
- id: fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: search
  name: '@deepseek-ai/dsh-tool-fs-search'
  config:
    sampleOverCapGlobResults: false
- id: skillfs
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: guard
  name: ./anti-escalation.mjs
"""

    def __init__(self, answers=None, error=None, *, preset_id="test-auditor",
                 composition=None, roster=None, write_result=True):
        self.answers = answers or {}
        self.error = error
        # Test-only stand-in for the *effective* DSH skill catalogue. The
        # evaluator reads this runtime state, not the corpus it is judging.
        self.effective_skills = {
            case["target_skill"] for case in corpus_compiler.compile_corpus(LIBRARY)["cases"]
        }
        self.seen = []
        self.prompts = []
        self.sessions = []
        self.cancelled = []
        self.supports_cancel = True
        self.preset_id = preset_id
        self.composition = (composition if composition is not None
                            else self.GOOD_COMPOSITION)
        self.roster = (roster if roster is not None
                       else [{"id": preset_id, "broken": False}])
        # Where the workspace the session was given. The fixture writes the
        # verdict there the way a mode does, so the read path under test is
        # the real one. Setting this False lets a test plant a tampered
        # ``result.json`` and leave it untouched.
        self.write_result = write_result
        self.roster_reads = []
        self.workspaces = {}

    # --- the authorized preset surface (agentPresets/*, never an "evaluator")
    def list_agent_presets(self):
        return {"value": {"items": [dict(row) for row in self.roster]}}

    def read_agent_preset(self, preset_id):
        self.roster_reads.append(preset_id)
        return {"value": {"agentPreset": preset_id,
                          "content": self.composition}}

    def create_creator_session(self, *, workspace_path=None,
                               agent_preset=None, session_id=None):
        session_id = f"sess-{len(self.sessions)}"
        self.sessions.append({
            "sessionId": session_id,
            "agentPreset": agent_preset,
            "workspace": str(workspace_path) if workspace_path else None,
        })
        if workspace_path:
            self.workspaces[session_id] = Path(workspace_path)
        return session_id

    def send_prompt(self, session_id, prompt, *, request_id=None):
        self.prompts.append((session_id, prompt))
        answer = self.answers.get(self._case_of(session_id))
        # A mode answers by persisting one JSON object, as the prompt asks.
        # Nothing is narrated in prose unless the test says so explicitly.
        workspace = self.workspaces.get(session_id)
        if workspace is None:
            return
        if not self.write_result:
            # The case workbook is already in the state the test planted: the
            # fixture does not touch it, so what the reader sees is exactly
            # what a tampered answer looks like.
            return
        if answer is None:
            return
        target = Path(workspace) / skill_gate_run.RESULT_FILENAME
        if isinstance(answer, bytes):
            target.write_bytes(answer)
        elif isinstance(answer, str):
            target.write_text(answer, encoding="utf-8")
        else:
            target.write_text(json.dumps(answer, ensure_ascii=False),
                              encoding="utf-8")

    def creator_observation(self, session_id, *, cursor=-1):
        self.seen.append(("session/page", {"sessionId": session_id}))
        if self.error is not None:
            raise self.error
        return {"cursor": 1, "events": [
            {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
            {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
            # The shape creator_client really emits: a flat events list. The
            # answer is never carried here -- only that the turn is over.
        ]}

    def _scenario_of(self, session_id):
        for session, prompt in self.prompts:
            if session == session_id:
                return json.loads(prompt)["case"]
        raise AssertionError("sin prompt para la sesion")

    def _case_of(self, session_id):
        return self._scenario_of(session_id)["case_id"]

    def cancel_session(self, session_id):
        if self.supports_cancel:
            self.cancelled.append(session_id)


class SkillGateRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-run-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)

    def _run(self, client, **kwargs):
        return skill_gate_run.run_corpus(
            client, self.corpus, mode=kwargs.pop("mode", "test-auditor"),
            candidate_digest=CAND_DIGEST, provider_name="fake",
            evaluator=kwargs.pop("evaluator", _FixtureEvaluator()), **kwargs)

    def test_every_case_produces_exactly_one_bound_observation(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        payload = self._run(client)
        self.assertEqual(len(payload["observations"]), len(self.corpus["cases"]))
        self.assertEqual(payload["corpus_digest"], self.corpus["corpus_digest"])
        self.assertEqual(payload["candidate_digest"], CAND_DIGEST)
        self.assertEqual(payload["provider"],
                         {"status": "available", "name": "fake"})

    def test_the_evaluator_prompt_never_carries_the_expected_verdict(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        self._run(client)
        self.assertEqual(len(client.prompts), len(self.corpus["cases"]))
        for _session_id, prompt in client.prompts:
            envelope = json.loads(prompt)
            case = envelope["case"]
            with self.subTest(case=case["case_id"]):
                # The instruction may name the verdict words -- it is a schema
                # the reader has to be able to fill. What must not travel is a
                # verdict about *this* case, or the answer it is judging.
                sent = json.dumps(case)
                self.assertNotIn("expected", sent)
                self.assertNotIn("corpus_digest", sent)
                self.assertNotIn("candidate_digest", sent)
                self.assertNotIn("verdict", sent)
                self.assertIn("task", case)

    def test_prompt_contains_all_public_fields_but_no_type_label(self):
        source = {case["case_id"]: case for case in self.corpus["cases"]}
        client = _FakeClient(answers={case["case_id"]:
                              {"verdict": "PASS", "evidence": "e"}
                              for case in self.corpus["cases"]})
        self._run(client)
        self.assertEqual(len(client.prompts), 55)
        for _, prompt in client.prompts:
            sent = json.loads(prompt)["case"]
            original = source[sent["case_id"]]
            with self.subTest(case=sent["case_id"]):
                self.assertEqual(set(sent), set(original["input"]) | {"case_id"})
                for key, value in original["input"].items():
                    self.assertEqual(sent[key], value)
                self.assertNotIn("type", sent)
                self.assertNotIn("expected", sent)
                self.assertNotIn("verdict", sent)
                self.assertNotIn("oracle", sent)

    def test_type_only_baseline_would_leak_the_answer(self):
        # This deliberately weak baseline assigns the majority verdict per
        # type without executing a single task. Its high score is precisely
        # why the classification label must not be sent to the model.
        from collections import Counter, defaultdict
        oracle = corpus_compiler.expected_verdicts(LIBRARY, self.corpus)
        grouped = defaultdict(Counter)
        for case, expected in zip(self.corpus["cases"], oracle):
            grouped[case["type"]][expected] += 1
        correct = sum(max(counts.values()) for counts in grouped.values())
        self.assertGreaterEqual(correct, 35)
        self.assertEqual(len(self.corpus["cases"]), 55)
        self.assertTrue(all("type" not in skill_gate_run._case_scenario(case)
                            for case in self.corpus["cases"]))

    def test_a_case_the_mode_answered_wrongly_is_reported_as_it_happened(self):
        # The gate exists to see wrong verdicts. A runner that normalizes them
        # to PASS would certify exactly what it was built to catch.
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        first = self.corpus["cases"][0]["case_id"]
        client.answers[first] = {"verdict": "BLOCKED", "evidence": "rechazado"}
        payload = self._run(client)
        verdicts = {o["case_id"]: o["verdict"] for o in payload["observations"]}
        self.assertEqual(verdicts[first], "BLOCKED")

    def test_unadapted_operational_preset_abstains_before_session_create(self):
        client = _FakeClient(answers={case["case_id"]:
                              {"verdict": "PASS", "evidence": "e"}
                              for case in self.corpus["cases"]})
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "layout fijo y 25 skills"):
            skill_gate_run.run_corpus(
                client, self.corpus, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake")
        self.assertEqual(client.sessions, [])
        self.assertEqual(client.prompts, [])

    def test_incomplete_evaluator_route_never_dispatches(self):
        class _Incomplete(_FixtureEvaluator):
            def prepare(self, client, corpus, mode, root):
                route = super().prepare(client, corpus, mode, root)
                route.pop(next(iter(route)))
                return route
        client = _FakeClient()
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "no verificó ruta"):
            self._run(client, evaluator=_Incomplete())
        self.assertEqual(client.sessions, [])

    def test_missing_effective_skill_never_dispatches(self):
        client = _FakeClient()
        client.effective_skills.remove(self.corpus["cases"][0]["target_skill"])
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "skill efectiva"):
            self._run(client)
        self.assertEqual(client.sessions, [])

    def test_incompatible_effective_skill_never_dispatches(self):
        class _MissingSkill(_FixtureEvaluator):
            def verify_case(self, client, case, preset, path):
                return case["case_id"] != "SC-129"
        client = _FakeClient()
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "skill efectiva"):
            self._run(client, evaluator=_MissingSkill())
        self.assertEqual(client.sessions, [])

    def test_a_case_that_could_not_run_is_not_covered_not_passed(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]}, error=RuntimeError("modo caído"))
        payload = self._run(client)
        self.assertTrue(all(o["verdict"] == "NOT_COVERED"
                            for o in payload["observations"]))
        self.assertIn("modo caído", payload["observations"][0]["evidence"])

    def test_an_answer_without_evidence_is_not_covered(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        first = self.corpus["cases"][0]["case_id"]
        client.answers[first] = {"verdict": "PASS", "evidence": "   "}
        payload = self._run(client)
        self.assertEqual(payload["observations"][0]["verdict"], "NOT_COVERED")

    def test_an_answer_with_an_unknown_verdict_is_not_covered(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        client.answers[self.corpus["cases"][0]["case_id"]] = {
            "verdict": "PROBABLY_FINE", "evidence": "e"}
        payload = self._run(client)
        self.assertEqual(payload["observations"][0]["verdict"], "NOT_COVERED")

    def test_the_written_observations_satisfy_the_bound_loader(self):
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS", "evidence": "e"}
            for case in self.corpus["cases"]})
        payload = self._run(client)
        path = skill_gate_run.write_observations(payload, self.tmp / "obs.json")
        loaded, seen = corpus_compiler.load_bound_observations(
            path, self.corpus, CAND_DIGEST)
        self.assertEqual(len(seen), len(self.corpus["cases"]))
        self.assertEqual(loaded["provider"]["name"], "fake")

    def test_a_run_with_no_session_produces_no_observations_at_all(self):
        # Not an empty list scored as zero: an unavailable provider cannot claim
        # observations, and the gate abstains on that basis.
        payload = skill_gate_run.abstain("no hay sesión DSH utilizable")
        self.assertEqual(payload["observations"] if "observations" in payload else [],
                         [])
        self.assertEqual(payload["provider"]["status"], "unavailable")
        self.assertIn("DSH", payload["reason"])

    def test_resolve_session_reports_the_concrete_missing_piece(self):
        # With no injected client it goes to the real acquisition code, and
        # whatever it lacks has to be named rather than swallowed.
        try:
            client = skill_gate_run.resolve_session()
        except skill_gate_run.RunnerUnavailable as error:
            self.assertTrue(str(error).strip(), "the reason must name something")
        else:
            self.assertIsNotNone(client)


class PersistedVerdictConfinementTest(unittest.TestCase):
    """``result.json`` is read under confinement, or the case is NOT_COVERED.

    The reader is the one hole in an otherwise closed gate: the mode under test
    writes into the case workspace, and whatever the reader will follow, read
    into memory or parse, is the mode's to choose. So the contract is pinned
    against every way that could be exploited -- a link out of the workspace, a
    file too big to read, a corrupt object, a PASS that only ever existed in
    prose -- and every one of them lands in an explicit NOT_COVERED, never in a
    fallback that scores something.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verdict-confine-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.case_dir = self.tmp / "case-x"
        self.case_dir.mkdir()

    def _persisted(self, workspace=None):
        return skill_gate_run._persisted_verdict(
            workspace if workspace is not None else self.case_dir)

    def _write_case_result(self, payload):
        target = self.case_dir / skill_gate_run.RESULT_FILENAME
        target.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
        return target

    def test_cancel_or_idle_cannot_read_even_a_persisted_pass(self):
        self._write_case_result({"verdict": "PASS", "evidence": "old"})
        for event_type in ("session/idle", "turn/cancel", "session/error",
                           "turn/error"):
            with self.subTest(event_type=event_type):
                class _Aborted:
                    def creator_observation(self, session_id, *, cursor=-1):
                        return {"cursor": 3, "events": [
                            {"type": "turn/start", "seq": 1,
                             "data": {"turn": 0}},
                            {"type": event_type, "seq": 2,
                             "data": {"turn": 0}},
                            {"type": "turn/end", "seq": 3,
                             "data": {"turn": 0}},
                        ]}
                self.assertIsNone(skill_gate_run._read_mode_verdict(
                    _Aborted(), "sess-old", 1, self.case_dir))

    def test_turn_end_with_error_reason_cannot_read_persisted_pass(self):
        self._write_case_result({"verdict": "PASS", "evidence": "old"})
        for reason in ("cancelled", "error", "failed", "aborted"):
            with self.subTest(reason=reason):
                class _Reason:
                    def creator_observation(self, session_id, *, cursor=-1):
                        return {"cursor": 2, "events": [
                            {"type": "turn/start", "seq": 1,
                             "data": {"turn": 0}},
                            {"type": "turn/end", "seq": 2,
                             "data": {"turn": 0, "reason": reason}},
                        ]}
                self.assertIsNone(skill_gate_run._read_mode_verdict(
                    _Reason(), "sess-old", 1, self.case_dir))

    def test_a_regular_object_in_the_case_workspace_is_read(self):
        self._write_case_result({"verdict": "PASS", "evidence": "observed"})
        self.assertEqual(self._persisted(),
                         {"verdict": "PASS", "evidence": "observed"})

    def test_a_missing_result_is_not_read(self):
        self.assertIsNone(self._persisted())

    def test_a_symlinked_result_is_refused(self):
        """The read is refused before it follows the link.

        A symlink turns the case workspace into a read of anywhere the mode
        under test can point at -- another case's answer, the operator's home,
        the corpus itself. The reader does not follow it; the case is simply
        not covered, and the mode learns nothing about what was pointed at.
        """
        outside = self.tmp / "elsewhere.json"
        outside.write_text(json.dumps(
            {"verdict": "PASS", "evidence": "not this case"}), encoding="utf-8")
        link = self.case_dir / skill_gate_run.RESULT_FILENAME
        link.symlink_to(outside)
        self.assertTrue(link.is_symlink())
        self.assertIsNone(self._persisted())

    def test_a_symlink_that_resolves_back_inside_is_still_refused(self):
        """The refusal is about the link itself, not only about where it lands.

        Refusing links only when they escape is a check that depends on the
        target, and a target the mode under test can make change after the
        check -- pointing back inside before the read, then out. The link is
        not followed at all, so there is nothing to race.
        """
        real = self.case_dir / "real.json"
        real.write_text(json.dumps(
            {"verdict": "PASS", "evidence": "announced"}), encoding="utf-8")
        link = self.case_dir / skill_gate_run.RESULT_FILENAME
        # The path goes out of the workspace and back in, so a
        # destination-based check would let it through.
        link.symlink_to(Path("..") / self.case_dir.name / "real.json")
        self.assertIsNone(self._persisted())

    def test_an_oversized_result_is_refused_before_it_is_read(self):
        """The budget is applied by stat, so the object is never loaded.

        A reader that counts bytes after reading has already paid for the
        megabyte it was handed, which is what makes an oversized object a
        resource problem rather than a contract problem.
        """
        target = self._write_case_result(
            {"verdict": "PASS", "evidence": "x" * 10})
        with open(target, "r+b") as stream:
            stream.truncate(skill_gate_run.RESULT_MAX_BYTES + 1)
        self.assertGreater(
            (self.case_dir / skill_gate_run.RESULT_FILENAME).stat().st_size,
            skill_gate_run.RESULT_MAX_BYTES)
        self.assertIsNone(self._persisted())

    def test_a_corrupt_result_is_not_a_verdict(self):
        target = self.case_dir / skill_gate_run.RESULT_FILENAME
        target.write_text('{"verdict": "PASS", "evidence":', encoding="utf-8")
        self.assertIsNone(self._persisted())

    def test_a_result_that_is_not_an_object_is_not_a_verdict(self):
        target = self.case_dir / skill_gate_run.RESULT_FILENAME
        target.write_text('"PASS"', encoding="utf-8")
        self.assertIsNone(self._persisted())

    def test_a_result_outside_the_bytes_it_declares_is_not_a_verdict(self):
        target = self.case_dir / skill_gate_run.RESULT_FILENAME
        target.write_bytes(b"\xff\xfe not utf-8 at all")
        self.assertIsNone(self._persisted())

    def test_a_fifo_is_refused(self):
        """A mode under test controls the case workspace: the reader must not
        open whatever it finds there, only a regular file."""
        target = self.case_dir / skill_gate_run.RESULT_FILENAME
        os.mkfifo(target)
        self.addCleanup(target.unlink)
        self.assertIsNone(self._persisted())


class VerdictShapeTest(unittest.TestCase):
    """What counts as an observation, and what never does."""

    def test_evidence_is_bounded_on_success_too(self):
        """The bound artifact is bounded in success, not only in failure.

        The observation file is published next to the report, so an answer
        that arrives with a megabyte of prose has to be cut on the way in. The
        truncation is announced, so an edited evidence is never mistaken for
        the one the mode wrote.
        """
        verdict, evidence = skill_gate_run._verdict_from(
            {"verdict": "PASS", "evidence": "z" * (skill_gate_run.MAX_EVIDENCE * 2)})
        self.assertEqual(verdict, "PASS")
        self.assertLessEqual(len(evidence), skill_gate_run.MAX_EVIDENCE)
        self.assertIn(skill_gate_run.EVIDENCE_TRUNCATION_MARK, evidence)

    def test_evidence_at_the_limit_is_kept_whole(self):
        verdict, evidence = skill_gate_run._verdict_from(
            {"verdict": "FAIL", "evidence": "z" * skill_gate_run.MAX_EVIDENCE})
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(evidence, "z" * skill_gate_run.MAX_EVIDENCE)
        self.assertNotIn(skill_gate_run.EVIDENCE_TRUNCATION_MARK, evidence)

    def test_a_narrated_pass_without_an_object_is_never_scored(self):
        """A model that describes its own success has produced prose.

        The folder of prose is the exact one that let a mode score itself; the
        answer now comes from one place only, and that place is a file.
        """
        self.assertEqual(skill_gate_run._read_mode_verdict(
            _NarratingObservations(), "sess-1", 1, None), None)

    def test_an_unknown_shape_is_not_covered(self):
        for response in (None, [], "PASS", 42,
                         {"verdict": "PASS"},
                         {"verdict": "PASS", "evidence": ""},
                         {"verdict": "PASS", "evidence": None},
                         {"verdict": "MAYBE", "evidence": "e"}):
            with self.subTest(response=response):
                verdict, _evidence = skill_gate_run._verdict_from(response)
                self.assertEqual(verdict, "NOT_COVERED")


class NotCoveredWaysTest(unittest.TestCase):
    """The whole set of ways a case fails to be covered, end to end.

    Each one of these is a way the gate could have shipped a PASS that no mode
    ever earned: a symlink handed back an answer written somewhere else, a file
    too large to be a contract, an object that is not the contract, a verdict
    that only ever existed in prose, a mode nobody named. None of them may
    reach the observation set as PASS.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="not-covered-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.first = self.corpus["cases"][0]["case_id"]
        self.answer = {"verdict": "PASS", "evidence": "ok"}

    def _run(self, client, mode="test-auditor"):
        return skill_gate_run.run_corpus(
            client, self.corpus, mode=mode,
            candidate_digest=CAND_DIGEST, provider_name="fake",
            workspace=self.tmp / "run", evaluator=_FixtureEvaluator())

    def _verdict_of(self, payload, case_id=None):
        wanted = case_id or self.first
        for observation in payload["observations"]:
            if observation["case_id"] == wanted:
                return observation
        raise AssertionError(f"sin observación para {wanted}")

    def _answers(self):
        return {case["case_id"]: self.answer
                for case in self.corpus["cases"]}

    def _plant(self, payload):
        """Plant an already-answered ``result.json`` the fixture will not touch.

        The tampered file has to survive the run for the reader to be the thing
        under test, so the fixture's own write is switched off and the file is
        planted by hand, exactly where a mode would have written it.
        """
        target = (self.tmp / "run" / self.first / skill_gate_run.RESULT_FILENAME)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.tmp / "run").chmod(0o700)
        if isinstance(payload, bytes):
            target.write_bytes(payload)
        else:
            target.write_text(payload, encoding="utf-8")
        return target

    def test_a_symlinked_result_is_not_covered_not_read(self):
        """The answer written by one run stops counting once it is a link.

        This is the shape of the exploit: a case that passed legitimately, then
        its own answer is replaced by a link to a file the gate never saw. A
        reader that follows links would keep reporting the earlier PASS.
        """
        self._plant(json.dumps({"verdict": "PASS", "evidence": "ok"}))
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps({"verdict": "PASS", "evidence": "ajeno"}),
                           encoding="utf-8")
        target = self.tmp / "run" / self.first / skill_gate_run.RESULT_FILENAME
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(_FakeClient(answers=self._answers(),
                                  write_result=False))
        self.assertIn("no es nuevo y exclusivo", str(ctx.exception))

    def test_an_oversized_result_is_not_covered(self):
        target = self._plant(b"x")
        with open(target, "r+b") as stream:
            stream.truncate(skill_gate_run.RESULT_MAX_BYTES + 1)
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(_FakeClient(answers=self._answers(),
                                  write_result=False))
        self.assertIn("no es nuevo y exclusivo", str(ctx.exception))

    def test_a_corrupt_result_is_not_covered(self):
        self._plant('{"verdict": "PASS",')
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(_FakeClient(answers=self._answers(),
                                  write_result=False))
        self.assertIn("no es nuevo y exclusivo", str(ctx.exception))

    def test_a_result_that_is_not_an_object_is_not_covered(self):
        self._plant('["PASS"]')
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(_FakeClient(answers=self._answers(),
                                  write_result=False))
        self.assertIn("no es nuevo y exclusivo", str(ctx.exception))

    def test_old_pass_with_nonwriting_client_cannot_be_reused(self):
        root = self.tmp / "old-run"
        root.mkdir(mode=0o700)
        client = _FakeClient(answers={self.first: self.answer})
        # First run writes a real answer; the remaining cases do not matter.
        first_only = json.loads(json.dumps(self.corpus))
        first_only["cases"] = first_only["cases"][:1]
        identity = {key: first_only[key] for key in
                    ("schema_version", "compiler_version", "source_digest", "cases")}
        first_only["corpus_digest"] = corpus_compiler._digest(identity)
        skill_gate_run.run_corpus(
            client, first_only, mode="test-auditor", candidate_digest=CAND_DIGEST,
            provider_name="fake", workspace=root, evaluator=_FixtureEvaluator())
        stale = root / self.first / skill_gate_run.RESULT_FILENAME
        self.assertTrue(stale.exists())
        no_write = _FakeClient(answers={self.first: self.answer},
                               write_result=False)
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "no es nuevo y exclusivo"):
            skill_gate_run.run_corpus(
                no_write, first_only, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=root, evaluator=_FixtureEvaluator())
        self.assertEqual(no_write.sessions, [])
        self.assertEqual(no_write.prompts, [])

    def test_a_symlinked_case_directory_is_rejected_before_dispatch(self):
        root = self.tmp / "symlink-run"
        root.mkdir(mode=0o700)
        target = self.tmp / "foreign"
        target.mkdir(mode=0o700)
        (target / skill_gate_run.RESULT_FILENAME).write_text(
            json.dumps(self.answer), encoding="utf-8")
        (root / self.first).symlink_to(target, target_is_directory=True)
        client = _FakeClient(answers=self._answers(), write_result=False)
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "no es nuevo y exclusivo"):
            skill_gate_run.run_corpus(
                client, self.corpus, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=root, evaluator=_FixtureEvaluator())
        self.assertEqual(client.sessions, [])

    def test_external_workspace_must_not_be_canonical_or_a_link(self):
        client = _FakeClient(answers=self._answers())
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "canónico"):
            skill_gate_run.run_corpus(
                client, self.corpus, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=ROOT / "gate-run-should-not-exist",
                evaluator=_FixtureEvaluator())
        link = self.tmp / "link"
        target = self.tmp / "target"
        target.mkdir(mode=0o700)
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "symlink"):
            skill_gate_run.run_corpus(
                client, self.corpus, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=link, evaluator=_FixtureEvaluator())
        self.assertEqual(client.sessions, [])
        self.assertFalse((ROOT / "gate-run-should-not-exist").exists())

    def test_case_id_traversal_is_rejected_before_a_workspace_is_created(self):
        client = _FakeClient(answers=self._answers())
        forged = json.loads(json.dumps(self.corpus))
        forged["cases"][0]["case_id"] = "../../.."
        identity = {key: forged[key] for key in
                    ("schema_version", "compiler_version", "source_digest", "cases")}
        forged["corpus_digest"] = corpus_compiler._digest(identity)
        root = self.tmp / "not-created"
        with self.assertRaisesRegex(corpus_compiler.CorpusError, "case_id"):
            skill_gate_run.run_corpus(
                client, forged, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=root, evaluator=_FixtureEvaluator())
        self.assertFalse(root.exists())
        self.assertEqual(client.sessions, [])

    def test_replaced_case_dir_before_session_create_is_not_dispatched(self):
        class _SwapCase(_FixtureEvaluator):
            def verify_case(self, client, case, preset, path):
                ok = super().verify_case(client, case, preset, path)
                if case["case_id"] == self.first:
                    moved = path.with_name("moved-case")
                    path.rename(moved)
                    path.symlink_to(moved, target_is_directory=True)
                return ok
        evaluator = _SwapCase()
        evaluator.first = self.first
        client = _FakeClient(answers=self._answers())
        with self.assertRaisesRegex(skill_gate_run.RunnerUnavailable,
                                    "sustituido"):
            skill_gate_run.run_corpus(
                client, self.corpus, mode="test-auditor",
                candidate_digest=CAND_DIGEST, provider_name="fake",
                workspace=self.tmp / "swapped", evaluator=evaluator)
        self.assertEqual(client.sessions, [])

    def test_a_result_at_the_run_root_counts_for_no_case(self):
        """The reader is bound to the case directory, not to the run root.

        ``run_corpus`` hands every case its own subdirectory. A mode under test
        that drops one ``result.json`` in the parent would otherwise have a
        single answer applied to all fifty-five cases, and a gate that read it
        would score a corpus from a single verdict nobody measured per case.
        """
        root = self.tmp / "run"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        (root / skill_gate_run.RESULT_FILENAME).write_text(
            json.dumps({"verdict": "PASS", "evidence": "uno para todas"}),
            encoding="utf-8")
        payload = self._run(_FakeClient(answers={}))
        for observation in payload["observations"]:
            with self.subTest(case=observation["case_id"]):
                self.assertEqual(observation["verdict"], "NOT_COVERED")
        self.assertNotIn("uno para todas",
                         json.dumps(payload, ensure_ascii=False))

    def test_a_missing_result_is_not_covered(self):
        # The fixture writes nothing for the first case: no object, no prose.
        answers = {case["case_id"]: self.answer
                   for case in self.corpus["cases"] if case["case_id"] != self.first}
        payload = self._run(_FakeClient(answers=answers))
        self.assertEqual(self._verdict_of(payload)["verdict"], "NOT_COVERED")

    def test_oversized_evidence_from_a_successful_mode_is_bounded(self):
        """The artifact is bounded on the way in, in success as well as in
        failure, and says that it was cut rather than silently dropping it."""
        client = _FakeClient(answers={
            case["case_id"]: {"verdict": "PASS",
                              "evidence": "observed " * 500}
            for case in self.corpus["cases"]})
        payload = self._run(client)
        observation = self._verdict_of(payload)
        verdict, evidence = observation["verdict"], observation["evidence"]
        self.assertEqual(verdict, "PASS")
        self.assertLessEqual(len(evidence), skill_gate_run.MAX_EVIDENCE)
        self.assertIn(skill_gate_run.EVIDENCE_TRUNCATION_MARK, evidence)

    def test_an_absent_mode_never_dispatches_and_never_passes(self):
        """``bootstrap.py skill-gate-run`` defaults ``--mode`` to empty, and an
        empty mode used to dispatch anyway, into whatever the Host boots.

        The refusal is a ``RunnerUnavailable``, which is the shape the launcher
        already handles as an abstention: nothing was fired at any client, and
        the run reports the missing piece instead of a corpus of unknowns.
        """
        client = _FakeClient(answers=self._answers())
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(client, mode="")
        self.assertIn("--mode", str(ctx.exception))
        self.assertEqual(client.sessions, [])

    def test_a_verified_preset_is_fetched_once_for_the_whole_corpus(self):
        """The verification is two RPCs; the corpus is fifty-five cases.

        Without the per-run cache the same preset would be asked of the roster
        again for every case, which is fifty-five extra reads of a composition
        nobody changed -- and a gate that cannot afford its own verification
        stops verifying.
        """
        client = _FakeClient(answers=self._answers())
        self._run(client)
        self.assertEqual(len(client.roster_reads), 1)
        self.assertGreaterEqual(len(client.sessions),
                                len(self.corpus["cases"]))

    def test_an_unverifiable_preset_refuses_the_whole_run(self):
        """A corpus run against a mode the roster does not list is refused,
        not averaged into fifty-five NOT_COVEREDs that look like coverage."""
        client = _FakeClient(answers=self._answers(), roster=[
            {"id": "some-other-mode", "broken": False}])
        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            self._run(client)
        self.assertIn("preset ausente", str(ctx.exception))
        self.assertEqual(client.sessions, [])


class _NarratingObservations:
    """The fold of a turn that ended having persisted nothing at all.

    The events say the turn ran and finished; the assistant text says, in
    perfectly good JSON, that everything passed. Neither is an observation.
    """

    def creator_observation(self, session_id, *, cursor=-1):
        return {"cursor": 1, "events": [
            {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
            {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
            {"type": "assistant/message", "seq": 3, "data": {
                "text": json.dumps({"verdict": "PASS", "evidence": "todo bien"})}}]}


class ModeVerificationTest(unittest.TestCase):
    """A mode the gate has not verified is a mode it does not dispatch."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mode-verify-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_an_absent_mode_is_a_refusal_naming_the_mode(self):
        detail = skill_gate_run._verify_mode(_VerifiedClient(), "")
        self.assertIn("--mode", detail)
        self.assertIn("ausente", detail)

    def test_a_blank_mode_is_a_refusal(self):
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                self.assertIsNotNone(
                    skill_gate_run._verify_mode(_VerifiedClient(), blank))

    def test_a_mode_that_is_not_a_string_is_a_refusal(self):
        self.assertIsNotNone(
            skill_gate_run._verify_mode(_VerifiedClient(), None))
        self.assertIsNotNone(
            skill_gate_run._verify_mode(_VerifiedClient(), ["auditor"]))

    def test_a_mode_absent_from_the_roster_is_a_refusal(self):
        client = _VerifiedClient(roster=[])
        detail = skill_gate_run._verify_mode(client, "ghost-mode")
        self.assertIn("preset ausente", detail)
        self.assertIn("ghost-mode", detail)

    def test_a_broken_preset_is_a_refusal(self):
        client = _VerifiedClient(roster=[{"id": "auditor", "broken": True}])
        detail = skill_gate_run._verify_mode(client, "auditor")
        self.assertIn("roto", detail)

    def test_a_preset_whose_composition_is_not_exact_is_a_refusal(self):
        """The composition is the contract that makes the write tool exist.

        A session missing an operational plugin boots without the framework's
        write contract, and the turn then fails for a reason that has nothing
        to do with the candidate -- scored as a FAIL or a NOT_COVERED of the
        wrong shape. The reader that decides whether a preset is dispatachable
        is ``workflow._verify_preset``, reused rather than reimplemented.
        """
        client = _VerifiedClient(composition="- id: persona\n  name: persona\n")
        detail = skill_gate_run._verify_mode(client, "auditor")
        self.assertIsNotNone(detail)
        self.assertIn("composición", detail)

    def test_a_client_without_the_preset_api_is_a_refusal(self):
        class _NoRoster:
            pass

        detail = skill_gate_run._verify_mode(_NoRoster(), "auditor")
        self.assertIn("no expone", detail)
        self.assertIn("list_agent_presets", detail)

    def test_the_dispatch_refuses_a_mode_it_did_not_verify(self):
        """The refusal happens before a session is created, not after a failed
        turn: nothing is dispatched, so no quota and no workspace are spent."""
        case = {"case_id": "case-x", "type": "realization",
                "input": {"task": "haz X", "target": "y"}}

        class _DispatchingClient:
            """A client whose roster does not list the mode, and whose session
            steps would shout if they were reached: the refusal has to happen
            before either."""

            def __init__(self):
                self.verified = _VerifiedClient(roster=[])
                self.sessions = []
                self.prompts = []

            def list_agent_presets(self):
                return self.verified.list_agent_presets()

            def read_agent_preset(self, preset_id):
                return self.verified.read_agent_preset(preset_id)

            def create_creator_session(self, **kwargs):
                self.sessions.append(kwargs)
                return "sess-1"

            def send_prompt(self, session_id, prompt, *, request_id=None):
                self.prompts.append(prompt)

            def creator_observation(self, session_id, *, cursor=-1):
                return {"cursor": 1, "events": []}

        client = _DispatchingClient()
        with self.assertRaises(RuntimeError) as ctx:
            skill_gate_run._dispatch(client, case, "ghost-mode", 1,
                                     self.tmp / "case-x")
        self.assertIn("preset ausente", str(ctx.exception))
        self.assertEqual(client.sessions, [])
        self.assertEqual(client.prompts, [])

        blank = _DispatchingClient()
        with self.assertRaises(RuntimeError) as ctx:
            skill_gate_run._dispatch(blank, case, "", 1,
                                     self.tmp / "case-x")
        self.assertIn("--mode", str(ctx.exception))
        self.assertEqual(blank.sessions, [])
        self.assertEqual(blank.prompts, [])


class _VerifiedClient:
    """A client that can be verified, so the verification itself is testable."""
    COMPOSITION = """- id: persona
  name: '@deepseek-ai/dsh-persona'
- id: bash
  name: '@deepseek-ai/dsh-tool-bash'
- id: fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: search
  name: '@deepseek-ai/dsh-tool-fs-search'
  config:
    sampleOverCapGlobResults: false
- id: skillfs
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: guard
  name: ./anti-escalation.mjs
"""

    def __init__(self, roster=None, composition=None):
        self.roster = roster if roster is not None else [
            {"id": "auditor", "broken": False}]
        self.composition = (composition if composition is not None
                            else self.COMPOSITION)
        self.reads = []

    def list_agent_presets(self):
        return {"value": {"items": [dict(row) for row in self.roster]}}

    def read_agent_preset(self, preset_id):
        self.reads.append(preset_id)
        return {"value": {"agentPreset": preset_id,
                          "content": self.composition}}


if __name__ == "__main__":
    unittest.main()
