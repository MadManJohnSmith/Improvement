"""Regression for the executable corpus and the identity-bound gate.

D11 was blocked because the 55 library scenarios were declarative assertion
tables: no task, no target, nothing an agent could be handed. These cases pin
the properties that make the corpus executable and the gate trustworthy, and
each one is a way a library change could ship unmeasured: a case that leaks its
own oracle, observations that do not match the corpus they claim, a provider
that reports results it never produced, and a trigger that waves through a
relevant change with no report at all.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus_compiler
import creator_client
import reflection
import skill_gate
import skill_gate_run

LIBRARY = ROOT / "library"
BASE_DIGEST = hashlib.sha256(b"baseline-candidate").hexdigest()
CAND_DIGEST = hashlib.sha256(b"candidate-under-test").hexdigest()


class ExecutableCorpusTest(unittest.TestCase):
    """The corpus compiles, deterministically, without publishing an oracle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="corpus-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.corpus_path = Path(self.tmp) / "corpus.json"
        corpus_compiler.write_corpus(self.corpus, self.corpus_path)

    def test_every_library_scenario_compiles_into_a_bounded_case(self):
        source = corpus_compiler._source_records(LIBRARY)
        self.assertEqual(len(source), 55)
        self.assertEqual(len(self.corpus["cases"]), len(source))
        self.assertEqual({c["case_id"] for c in self.corpus["cases"]},
                         {r["scenario_id"] for _, r in source})

    def test_each_case_carries_a_task_and_resolves_its_skill(self):
        skills = corpus_compiler._skill_names(LIBRARY)
        for case in self.corpus["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertTrue(case["input"]["task"])
                self.assertIn(case["target_skill"], skills)
                self.assertEqual(case["input"]["target"], case["target_skill"])

    def test_compilation_is_deterministic(self):
        again = corpus_compiler.compile_corpus(LIBRARY)
        self.assertEqual(again, self.corpus)
        self.assertEqual(again["corpus_digest"], self.corpus["corpus_digest"])

    def test_public_cases_never_carry_the_expected_verdict(self):
        # The public case is what the mode under test receives. If the answer
        # travels with the question, the gate measures reading, not skill.
        for case in self.corpus["cases"]:
            with self.subTest(case=case["case_id"]):
                serialized = json.dumps(case)
                self.assertNotIn("expected", serialized)
                self.assertNotIn("verdict", serialized)
                self.assertNotIn("oracle", serialized)

    def test_every_compiled_case_retains_its_source_semantics(self):
        sources = {scenario["scenario_id"]: scenario
                   for _, scenario in corpus_compiler._source_records(LIBRARY)}
        for case in self.corpus["cases"]:
            with self.subTest(case=case["case_id"]):
                source = sources[case["case_id"]]
                self.assertEqual(case["input"]["scenario_fixture"],
                                 source["input"])
                self.assertEqual(case["input"]["scenario_description"],
                                 source["description"])
                self.assertNotIn("expected", case["input"])
                self.assertNotIn("verdict", case["input"])

    def test_oracles_come_from_the_host_side_source(self):
        verdicts = corpus_compiler.expected_verdicts(LIBRARY, self.corpus)
        self.assertEqual(len(verdicts), len(self.corpus["cases"]))
        self.assertEqual(set(verdicts),
                         {"PASS", "FAIL", "BLOCKED", "NOT_COVERED"})

    def test_oracles_refuse_a_corpus_that_does_not_match_the_source(self):
        # A corpus compiled from different sources would score scenarios the
        # oracles do not describe. The digest is what catches it.
        tampered = json.loads(json.dumps(self.corpus))
        tampered["cases"][0]["input"]["task"] = "something else entirely"
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.expected_verdicts(LIBRARY, tampered)

    def test_case_id_cannot_escape_the_host_workspace(self):
        # Even a self-consistent forged corpus digest must not turn a case_id
        # into a relative path or a symlink-readable neighbour's answer.
        for case_id in ("../../..", "../SC-101", "SC-101/../SC-102",
                        "/tmp/SC-101", "SC-101\\result", "SC-101\n", "."):
            with self.subTest(case_id=case_id):
                forged = json.loads(json.dumps(self.corpus))
                forged["cases"][0]["case_id"] = case_id
                identity = {key: forged[key] for key in
                            ("schema_version", "compiler_version",
                             "source_digest", "cases")}
                forged["corpus_digest"] = corpus_compiler._digest(identity)
                with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                            "case_id"):
                    corpus_compiler.validate_corpus(forged)

    def test_oracle_fields_cannot_hide_in_a_public_fixture(self):
        for key in ("expected", "verdict", "oracle", "evidence_type", "type"):
            with self.subTest(key=key):
                forged = json.loads(json.dumps(self.corpus))
                forged["cases"][0]["input"]["scenario_fixture"][key] = "PASS"
                identity = {name: forged[name] for name in
                            ("schema_version", "compiler_version",
                             "source_digest", "cases")}
                forged["corpus_digest"] = corpus_compiler._digest(identity)
                with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                            "exposes an oracle"):
                    corpus_compiler.validate_corpus(forged)

    def test_nested_public_input_cannot_smuggle_oracle_field(self):
        forged = json.loads(json.dumps(self.corpus))
        forged["cases"][0]["input"]["scenario_fixture"]["nested"] = {
            "verdict": "PASS"}
        identity = {key: forged[key] for key in
                    ("schema_version", "compiler_version", "source_digest", "cases")}
        forged["corpus_digest"] = corpus_compiler._digest(identity)
        with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                    "exposes an oracle"):
            corpus_compiler.validate_corpus(forged)

    def test_source_scenario_input_cannot_smuggle_oracle_field(self):
        library = Path(self.tmp) / "library"
        shutil.copytree(LIBRARY, library)
        path = library / "base/brainstorming/scenarios/SC-101.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["input"]["verdict"] = "PASS"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                    "exposes an oracle"):
            corpus_compiler.compile_corpus(library)

    def test_an_unknown_scenario_type_is_refused_not_guessed(self):
        library = Path(self.tmp) / "library"
        shutil.copytree(LIBRARY, library)
        path = library / "base/brainstorming/scenarios/SC-101.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["type"] = "vibes-based"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.compile_corpus(library)

    def test_a_target_skill_that_resolves_nowhere_is_refused(self):
        library = Path(self.tmp) / "library-orphan"
        shutil.copytree(LIBRARY, library)
        path = library / "base/brainstorming/scenarios/SC-101.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["target_skill"] = "skill-that-does-not-exist"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.compile_corpus(library)


class BoundObservationsTest(unittest.TestCase):
    """Observations are only evidence when they are tied to what produced them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="observations-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.ids = [case["case_id"] for case in self.corpus["cases"]]

    def _payload(self, digest=CAND_DIGEST, verdicts=None, status="available",
                 corpus_digest=None, observations=None):
        verdicts = verdicts if verdicts is not None else ["PASS"] * len(self.ids)
        return {
            "schema_version": 1,
            "compiler_version": self.corpus["compiler_version"],
            "corpus_digest": corpus_digest or self.corpus["corpus_digest"],
            "candidate_digest": digest,
            "provider": ({"status": status, "name": "regression-provider"}
                         if status == "available" else {"status": status}),
            "observations": observations if observations is not None else [
                {"case_id": case_id, "verdict": verdict, "evidence": "e"}
                for case_id, verdict in zip(self.ids, verdicts)],
        }

    def _write(self, name, payload):
        path = Path(self.tmp) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_a_complete_observation_set_is_accepted(self):
        payload = self._payload()
        self.corpus_compiler_check(payload)

    def corpus_compiler_check(self, payload):
        value, seen = corpus_compiler.load_bound_observations(
            self._write("obs.json", payload), self.corpus, CAND_DIGEST)
        self.assertEqual(len(seen), len(self.ids))
        self.assertEqual(value["candidate_digest"], CAND_DIGEST)

    def test_observations_for_another_corpus_are_refused(self):
        # The failure this prevents: scores carried over from a corpus that was
        # edited after the run, which is a PASS for a question nobody asked.
        payload = self._payload(corpus_digest=hashlib.sha256(b"other").hexdigest())
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)

    def test_observations_for_another_candidate_are_refused(self):
        path = self._write("obs.json", self._payload())
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                path, self.corpus, hashlib.sha256(b"other").hexdigest())

    def test_incomplete_observations_are_refused(self):
        payload = self._payload(observations=[
            {"case_id": self.ids[0], "verdict": "PASS", "evidence": "e"}])
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)

    def test_duplicate_case_observations_are_refused(self):
        payload = self._payload(observations=[
            {"case_id": self.ids[0], "verdict": "PASS", "evidence": "e"},
            {"case_id": self.ids[0], "verdict": "FAIL", "evidence": "e"}])
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)

    def test_an_unavailable_provider_cannot_also_claim_observations(self):
        payload = self._payload(status="unavailable")
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)

    def test_an_available_provider_must_name_itself(self):
        payload = self._payload()
        payload["provider"] = {"status": "available"}
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)

    def test_evidence_is_required_for_every_observation(self):
        payload = self._payload(observations=[
            {"case_id": case_id, "verdict": "PASS", "evidence": ""}
            for case_id in self.ids])
        with self.assertRaises(corpus_compiler.CorpusError):
            corpus_compiler.load_bound_observations(
                self._write("obs.json", payload), self.corpus, CAND_DIGEST)


class BoundGateTest(unittest.TestCase):
    """The gate's four decisions, against the real 55-scenario corpus."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bound-gate-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.corpus_path = Path(self.tmp) / "corpus.json"
        corpus_compiler.write_corpus(self.corpus, self.corpus_path)
        self.ids = [case["case_id"] for case in self.corpus["cases"]]
        self.truth = corpus_compiler.expected_verdicts(LIBRARY, self.corpus)
        _, validation = skill_gate.split_scenarios(
            skill_gate.load_scenarios(LIBRARY), 0.3)
        self.validation_ids = {scenario["scenario_id"] for scenario in validation}

    def _observations(self, name, digest, verdicts, status="available"):
        payload = {
            "schema_version": 1,
            "compiler_version": self.corpus["compiler_version"],
            "corpus_digest": self.corpus["corpus_digest"],
            "candidate_digest": digest,
            "provider": ({"status": status, "name": "regression-provider"}
                         if status == "available" else {"status": status}),
            "observations": [] if status != "available" else [
                {"case_id": case_id, "verdict": verdict, "evidence": "e"}
                for case_id, verdict in zip(self.ids, verdicts)],
        }
        path = Path(self.tmp) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _gate(self, baseline, candidate):
        return skill_gate.evaluate_bound_gate(
            baseline, candidate, self.corpus_path,
            BASE_DIGEST, CAND_DIGEST, 0.3, LIBRARY)

    def test_a_candidate_that_fixes_held_out_failures_is_accepted(self):
        # The one way the gate says yes. Everything else about it stays equal.
        improved, fixed = [], set()
        for case_id, expected in zip(self.ids, self.truth):
            if (case_id in self.validation_ids and expected == "PASS"
                    and len(fixed) < 3):
                fixed.add(case_id)
                improved.append("FAIL")
            else:
                improved.append(expected)
        candidate = ["PASS" if case_id in fixed else verdict
                     for case_id, verdict in zip(self.ids, improved)]
        report = self._gate(
            self._observations("base.json", BASE_DIGEST, improved),
            self._observations("cand.json", CAND_DIGEST, candidate))
        self.assertEqual(report["action"], "accept", report)
        self.assertEqual(report["reasons"], [])

    def test_a_candidate_that_changes_nothing_is_refused(self):
        # Equal is not better: this is the shape of a change that ships itself.
        report = self._gate(
            self._observations("base.json", BASE_DIGEST, self.truth),
            self._observations("cand.json", CAND_DIGEST, self.truth))
        self.assertEqual(report["action"], "reject", report)
        self.assertTrue(any("holdout" in reason for reason in report["reasons"]),
                        report)

    def test_a_candidate_that_wins_held_out_and_loses_the_rest_is_refused(self):
        improved, fixed = [], set()
        for case_id, expected in zip(self.ids, self.truth):
            if (case_id in self.validation_ids and expected == "PASS"
                    and len(fixed) < 3):
                fixed.add(case_id)
                improved.append("FAIL")
            else:
                improved.append(expected)
        candidate = ["PASS" if case_id in fixed else verdict
                     for case_id, verdict in zip(self.ids, improved)]
        # Now break exactly one training case, leaving the held-out gain intact.
        training_pass = next(
            case_id for case_id, expected in zip(self.ids, self.truth)
            if case_id not in self.validation_ids and expected == "PASS")
        candidate[self.ids.index(training_pass)] = "FAIL"
        report = self._gate(
            self._observations("base.json", BASE_DIGEST, improved),
            self._observations("cand.json", CAND_DIGEST, candidate))
        self.assertEqual(report["action"], "reject", report)
        self.assertTrue(any("entrenamiento" in reason for reason in report["reasons"]),
                        report)

    def test_without_a_provider_the_gate_abstains(self):
        # A gate that cannot prove anything says so instead of returning a number.
        report = self._gate(
            self._observations("base.json", BASE_DIGEST, [], status="unavailable"),
            self._observations("cand.json", CAND_DIGEST, self.truth))
        self.assertEqual(report["action"], "abstain", report)
        self.assertTrue(report["reasons"], report)

    def test_the_report_binds_corpus_and_both_candidates(self):
        report = self._gate(
            self._observations("base.json", BASE_DIGEST, self.truth),
            self._observations("cand.json", CAND_DIGEST, self.truth))
        self.assertEqual(report["corpus_digest"], self.corpus["corpus_digest"])
        self.assertEqual(report["baseline_candidate_digest"], BASE_DIGEST)
        self.assertEqual(report["candidate_digest"], CAND_DIGEST)
        self.assertEqual(report["compiler_version"],
                         self.corpus["compiler_version"])


class CommitTriggerTest(unittest.TestCase):
    """A relevant change is gated; an unrelated one is not blocked."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trigger-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.corpus_path = Path(self.tmp) / "corpus.json"
        corpus_compiler.write_corpus(self.corpus, self.corpus_path)
        self.report_path = Path(self.tmp) / "report.json"

    def _write_report(self, action):
        self.report_path.write_text(json.dumps({
            "schema_version": 1,
            "compiler_version": self.corpus["compiler_version"],
            "corpus_digest": self.corpus["corpus_digest"],
            "baseline_candidate_digest": BASE_DIGEST,
            "candidate_digest": CAND_DIGEST,
            "action": action,
            "reasons": [] if action == "accept" else ["held-out did not improve"],
        }), encoding="utf-8")

    def test_a_relevant_change_without_a_report_is_blocked(self):
        with self.assertRaises(ValueError):
            skill_gate.commit_trigger_check(
                ["library/base/brainstorming/SKILL.md"], None,
                self.corpus["corpus_digest"], CAND_DIGEST)

    def test_a_rejecting_report_blocks_the_change(self):
        self._write_report("reject")
        with self.assertRaises(ValueError):
            skill_gate.commit_trigger_check(
                ["library/base/brainstorming/SKILL.md"], self.report_path,
                self.corpus["corpus_digest"], CAND_DIGEST)

    def test_an_abstaining_report_blocks_the_change(self):
        # Abstention is not permission. This is the whole point of the trigger.
        self._write_report("abstain")
        with self.assertRaises(ValueError):
            skill_gate.commit_trigger_check(
                ["library/base/brainstorming/SKILL.md"], self.report_path,
                self.corpus["corpus_digest"], CAND_DIGEST)

    def test_a_report_for_another_candidate_blocks_the_change(self):
        self._write_report("accept")
        with self.assertRaises(corpus_compiler.CorpusError):
            skill_gate.commit_trigger_check(
                ["library/base/brainstorming/SKILL.md"], self.report_path,
                self.corpus["corpus_digest"],
                hashlib.sha256(b"some other candidate").hexdigest())

    def test_an_accepting_report_lets_the_change_through(self):
        self._write_report("accept")
        outcome = skill_gate.commit_trigger_check(
            ["library/base/brainstorming/SKILL.md", "scripts/skill_gate.py"],
            self.report_path, self.corpus["corpus_digest"], CAND_DIGEST)
        self.assertEqual(outcome, {"required": True, "accepted": True})

    def test_changes_outside_the_corpus_are_not_gated(self):
        # A gate that blocks every commit is a gate people disable.
        outcome = skill_gate.commit_trigger_check(
            ["README.md", "docs/usage.md"], None,
            self.corpus["corpus_digest"], CAND_DIGEST)
        self.assertEqual(outcome, {"required": False, "accepted": True})


class BoundGateExitCodeTest(unittest.TestCase):
    """A decision command has to carry its decision in the exit code.

    Found by running the documented command: it reported `reject`, wrote the
    report, and still exited 0. A CI step that reads only `$?` would have
    merged a candidate the gate just refused.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="exit-code-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)
        self.corpus_path = Path(self.tmp) / "corpus.json"
        corpus_compiler.write_corpus(self.corpus, self.corpus_path)
        self.ids = [case["case_id"] for case in self.corpus["cases"]]
        self.truth = corpus_compiler.expected_verdicts(LIBRARY, self.corpus)
        _, validation = skill_gate.split_scenarios(
            skill_gate.load_scenarios(LIBRARY), 0.3)
        self.validation_ids = {s["scenario_id"] for s in validation}

    def _cli(self, *arguments):
        # shutil.which('python3') and not sys.executable: in this host
        # sys.executable is the ZCode AppImage, which starts a GUI.
        return subprocess.run(
            [shutil.which("python3"), "-B", str(ROOT / "scripts" / "bootstrap.py"),
             *arguments],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def _observations(self, name, digest, verdicts):
        path = Path(self.tmp) / name
        path.write_text(json.dumps({
            "schema_version": 1,
            "compiler_version": self.corpus["compiler_version"],
            "corpus_digest": self.corpus["corpus_digest"],
            "candidate_digest": digest,
            "provider": {"status": "available", "name": "regression-provider"},
            "observations": [{"case_id": case_id, "verdict": verdict,
                              "evidence": "e"}
                             for case_id, verdict in zip(self.ids, verdicts)],
        }), encoding="utf-8")
        return path

    def _improving_pair(self):
        baseline, fixed = [], set()
        for case_id, expected in zip(self.ids, self.truth):
            if (case_id in self.validation_ids and expected == "PASS"
                    and len(fixed) < 3):
                fixed.add(case_id)
                baseline.append("FAIL")
            else:
                baseline.append(expected)
        candidate = ["PASS" if case_id in fixed else verdict
                     for case_id, verdict in zip(self.ids, baseline)]
        return baseline, candidate

    def test_a_rejected_candidate_exits_non_zero_and_still_prints_the_report(self):
        finished = self._cli(
            "bound-skill-gate", "--corpus", str(self.corpus_path),
            "--baseline", str(self._observations("b.json", BASE_DIGEST, self.truth)),
            "--candidate", str(self._observations("c.json", CAND_DIGEST, self.truth)),
            "--baseline-digest", BASE_DIGEST, "--candidate-digest", CAND_DIGEST,
            "--report", str(Path(self.tmp) / "rejected.json"))
        self.assertEqual(finished.returncode, 1, finished.stdout + finished.stderr)
        self.assertIn('"RETAINED"', finished.stdout)
        self.assertTrue((Path(self.tmp) / "rejected.json").is_file())

    def test_an_accepted_candidate_exits_zero(self):
        baseline, candidate = self._improving_pair()
        finished = self._cli(
            "bound-skill-gate", "--corpus", str(self.corpus_path),
            "--baseline", str(self._observations("b2.json", BASE_DIGEST, baseline)),
            "--candidate", str(self._observations("c2.json", CAND_DIGEST, candidate)),
            "--baseline-digest", BASE_DIGEST, "--candidate-digest", CAND_DIGEST,
            "--report", str(Path(self.tmp) / "accepted.json"))
        self.assertEqual(finished.returncode, 0, finished.stdout + finished.stderr)
        self.assertIn('"RESOLVED"', finished.stdout)

    def test_the_refusal_is_kept_so_the_next_attempt_is_not_the_same_one(self):
        """A gate that only says no is half a loop.

        The refusal was printed and then discarded: the next editor started
        from nothing, proposed something the corpus had already refused, and
        paid a full agent run to be told the same thing. That is the same
        repetition E2 paid for in the defect memory, in the place where it costs
        the most, and SkillOpt's design — recorded in the source registry — puts
        a buffer of rejected edits with before/after scores precisely so the
        reflection has something to read.

        Three things have to hold, and each is a different failure if it does
        not: the refusal is recorded with the held-out scores, a re-send of the
        exact candidate is refused *before* scoring, and a refusal from another
        corpus blocks nothing, because it answered a different question.
        """
        buffer = Path(self.tmp) / "reflection.jsonl"
        rejected = self._cli(
            "bound-skill-gate", "--corpus", str(self.corpus_path),
            "--baseline", str(self._observations("rb.json", BASE_DIGEST, self.truth)),
            "--candidate", str(self._observations("rc.json", CAND_DIGEST, self.truth)),
            "--baseline-digest", BASE_DIGEST, "--candidate-digest", CAND_DIGEST,
            "--report", str(Path(self.tmp) / "r.json"), "--buffer", str(buffer))
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        entries = reflection.read(buffer)
        self.assertEqual(len(entries), 1, entries)
        self.assertEqual(entries[0]["candidate_digest"], CAND_DIGEST)
        self.assertEqual(entries[0]["corpus_digest"], self.corpus["corpus_digest"])
        self.assertEqual(entries[0]["action"], "reject")
        # The scores are what make a second attempt different rather than new.
        self.assertIsInstance(entries[0].get("baseline_validation"), float)
        self.assertIsInstance(entries[0].get("candidate_validation"), float)

        # The brief is what the next attempt reads.
        brief = json.loads(self._cli(
            "skill-gate-reflect", "--buffer", str(buffer),
            "--corpus-digest", self.corpus["corpus_digest"]).stdout)["reflection"]
        self.assertEqual(brief["entries"][0]["candidate_digest"], CAND_DIGEST)
        self.assertIn("holdout", brief["entries"][0]["score"])

        # Re-sending the identical candidate is refused without scoring it: the
        # observations file is deleted first, so reaching the gate at all would
        # raise, and a clean refusal proves the check ran early.
        (Path(self.tmp) / "rc.json").unlink()
        again = self._cli(
            "bound-skill-gate", "--corpus", str(self.corpus_path),
            "--baseline", str(self._observations("rb.json", BASE_DIGEST, self.truth)),
            "--candidate", str(Path(self.tmp) / "rc.json"),
            "--baseline-digest", BASE_DIGEST, "--candidate-digest", CAND_DIGEST,
            "--report", str(Path(self.tmp) / "r2.json"), "--buffer", str(buffer))
        self.assertEqual(again.returncode, 1, again.stdout + again.stderr)
        self.assertIn("ya fue rechazada", again.stdout)
        self.assertFalse((Path(self.tmp) / "r2.json").exists())

        # A different corpus answers a different question, so its refusals do
        # not travel.
        other = json.loads(self._cli(
            "skill-gate-reflect", "--buffer", str(buffer),
            "--corpus-digest", "f" * 64).stdout)["reflection"]
        self.assertEqual(other["entries"], [])
        self.assertEqual(other["total_refusals"], 1)

    def test_the_refusal_loop_holds_its_own_invariants(self):
        """The buffer is a memory, so it inherits the memory's hard parts.

        Append in place, because a temp file plus `os.replace` would drop every
        earlier refusal — the exact defect the episodic ledger shipped with. An
        accept is not recorded: a buffer that also collects successes becomes a
        changelog. A torn trailing line is a crash and is skipped; corruption
        before it is refused, because a silently shortened memory forgets a
        refusal the gate once gave.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            buffer = Path(tmp) / "b.jsonl"
            corpus, candidate = "a" * 64, "b" * 64
            reflection.record(buffer, corpus_digest=corpus,
                              candidate_digest=candidate, action="reject",
                              reasons=["el holdout no mejora"],
                              baseline=0.6, candidate=0.5)
            reflection.record(buffer, corpus_digest=corpus,
                              candidate_digest="c" * 64, action="reject",
                              reasons=["regresión en entrenamiento"])
            self.assertEqual(len(reflection.read(buffer)), 2)
            with self.assertRaisesRegex(reflection.ReflectionError, "solo se recuerdan"):
                reflection.record(buffer, corpus_digest=corpus,
                                  candidate_digest="d" * 64, action="accept",
                                  reasons=[])
            with self.assertRaisesRegex(reflection.ReflectionError, "sha256"):
                reflection.record(buffer, corpus_digest="no-es-digest",
                                  candidate_digest="d" * 64, action="reject",
                                  reasons=["x"])
            # A crash between the write and the newline is skipped, not fatal.
            with buffer.open("a", encoding="utf-8") as stream:
                stream.write('{"version":1,"corpus')
            self.assertEqual(len(reflection.read(buffer)), 2)
            # Corruption before the last line is refused.
            buffer.write_text('{"nope"\n' + buffer.read_text(), encoding="utf-8")
            with self.assertRaisesRegex(reflection.ReflectionError, "línea inválida"):
                reflection.read(buffer)

    def test_the_legacy_gate_keeps_its_published_exit_zero(self):
        # Changing an already published command's contract would break callers
        # that read the verdict from stdout; the bound path is the new contract.
        legacy = Path(self.tmp) / "legacy.json"
        payload = {"scenarios": {case_id: verdict
                                 for case_id, verdict in zip(self.ids, self.truth)}}
        legacy.write_text(json.dumps(payload), encoding="utf-8")
        finished = self._cli(
            "skill-gate", "--baseline", str(legacy), "--candidate", str(legacy),
            "--library", str(LIBRARY))
        self.assertEqual(finished.returncode, 0, finished.stdout + finished.stderr)


class DshHeadlessCompositionRegression(unittest.TestCase):
    """The headless session the framework launches carries the framework overlay.

    A Creator pilot turn came back RETAINED because a headless turn boots
    without ``workflow_write``: the overlay is only applied by ``launch_dsh_web``,
    and a session started by any other route answers the framework's write
    contract with the upstream tool the sandbox rejects. One resolver
    (``creator_client.dsh_headless_command``) and one entry point per profile
    is what keeps the two from drifting again, and these cases pin the three
    things that would drift: the launcher flag, the overlay row, and the tool
    name the overlay registers.
    """

    def test_the_headless_command_carries_the_plugin_overlay(self):
        command = creator_client.dsh_headless_command()
        # `--patch` is a launcher flag, so it composes with any profile -- the
        # headless one included. Without it the row is simply absent.
        self.assertEqual(command[-2:-1], ["--patch"])
        self.assertEqual(Path(command[-1]), creator_client.DSH_PLUGIN_PATCH)
        self.assertEqual(command[:5], ["npx", "-y", "@deepseek-ai/dsh",
                                       "--profile", "headless"])

    def test_the_headless_overlay_row_resolves_to_the_workflow_write_plugin(self):
        """A row that pointed anywhere else would boot without the tool."""
        overlay = creator_client.DSH_PLUGIN_PATCH.read_text(encoding="utf-8")
        rows = [line.strip() for line in overlay.splitlines()
                if line.strip().startswith("- ")]
        # The overlay is an `insert` row carrying exactly one plugin. A second
        # row would be a second overlay that nobody reviewed.
        self.assertEqual(rows, ["- insert:", "- name: ./workflow-write.mjs"],
                         f"overlay con filas inesperadas: {rows}")
        plugin = creator_client.DSH_PLUGIN_PATCH.parent / "workflow-write.mjs"
        self.assertTrue(plugin.is_file(),
                        "la fila del overlay no resuelve a un plugin real")

    def test_the_overlay_registers_the_tool_the_framework_promises(self):
        """The tool name in the source is the one the framework's instructions
        promise. A rename here would pass an audit by inspection."""
        source = (creator_client.DSH_PLUGIN_PATCH.parent / "workflow-write.mjs"
                  ).read_text(encoding="utf-8")
        registration = source[source.index("ctx.tools.register("):]
        self.assertIn("name: 'workflow_write'", registration)
        # The framework's own instructions tell generated modes to call
        # workflow_write and never plain write. A session booted without the
        # overlay would follow those instructions into the upstream rejection.
        instructions = Path(creator_client.__file__).read_text(encoding="utf-8")
        self.assertIn("usa el tool `workflow_write` (no `write`)", instructions)

    def test_the_headless_command_honours_the_shared_escape_hatch(self):
        """The headless route reuses the web resolver rather than redefining it,
        so its escape hatch is the same one the launcher documents."""
        patched = creator_client.dsh_headless_command()
        with unittest.mock.patch.dict(os.environ,
                                      {"DSH_PLUGIN_PATCH": "0"}):
            bare = creator_client.dsh_headless_command()
        self.assertEqual(bare, patched[:len(patched) - 2])
        self.assertNotIn("--patch", bare)


class _RosterClient:
    """The authorized preset surface any dispatch fixture can stand on.

    Kept at module level so a fixture subclass does not depend on enclosing
    class scoping. It answers the same two RPCs the real client serves --
    ``agentPresets/list`` and ``agentPresets/read`` -- with the exact
    operational composition, because the runner refuses to dispatch against a
    mode it has not verified. A fixture that omits the roster tests something
    weaker than it looks like: it proves the refusal, not the dispatch.
    """

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

    def __init__(self, preset_id="auditor"):
        self.preset_id = preset_id

    def list_agent_presets(self):
        return {"value": {"items": [
            {"id": self.preset_id, "broken": False}]}}

    def read_agent_preset(self, preset_id):
        return {"value": {"agentPreset": preset_id,
                          "content": self.COMPOSITION}}


class SkillGateRunContractRegression(unittest.TestCase):
    """The corpus gate names the endpoint DSH does not have, and admits it.

    A previous revision called an ``evaluator`` RPC that DSH 0.2.0-rc.2 never
    exposed: a call to a method that does not exist answers 404 at best and a
    fabricated verdict at worst, and a gate that has to publish an observation
    will fill in whatever it needs to. The dispatch now goes through the session
    API that release really serves, and a client that cannot serve it
    refuses with the missing piece named -- never with an invented verdict.

    Every client fixture here subclasses ``_RosterClient``, the authorized
    preset surface, because the runner refuses to dispatch against a mode it
    has not verified. A fixture that quietly omits the roster tests something
    weaker than it looks like: it proves the refusal, not the dispatch.
    """

    def _case(self):
        return {
            "case_id": "case-x", "type": "realization",
            "input": {"task": "haz X", "target": "y"},
        }

    def test_a_client_without_the_session_api_never_yields_a_verdict(self):
        class _OnlyRpc:
            def rpc(self, endpoint, request=None, timeout=30):
                raise AssertionError(
                    "el gate no debe llamar a un endpoint inexistente")

        client = _OnlyRpc()
        with self.assertRaises(RuntimeError) as ctx:
            skill_gate_run._dispatch(client, self._case(), "auditor", 1, None)
        message = str(ctx.exception)
        self.assertIn("create_creator_session", message)
        self.assertIn("session/create", message)

    def test_the_refusal_names_the_absent_endpoint_rather_than_success(self):
        """What the message says, in full, is the measured carency."""
        with self.assertRaises(RuntimeError) as ctx:
            skill_gate_run._dispatch(object(), self._case(), "auditor", 1, None)
        message = str(ctx.exception)
        self.assertIn("no expone", message)
        self.assertIn("session/create", message)
        self.assertIn("evaluator", message)

    def test_a_case_that_ran_but_was_not_answered_is_not_covered(self):
        class _Client(_RosterClient):
            def create_creator_session(self, **kwargs):
                return "sess-1"
            def send_prompt(self, session_id, prompt, *, request_id=None):
                pass
            def creator_observation(self, session_id, *, cursor=-1):
                # A turn that ended with prose and no object to parse.
                return {"cursor": 1, "events": [
                    {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
                    {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
                    {"type": "assistant/message", "seq": 3,
                     "data": {"text": "no pude responder"}},
                ]}
            def cancel_session(self, session_id):
                pass

        verdict, evidence = skill_gate_run._dispatch(
            _Client(), self._case(), "auditor", 5, None)
        self.assertEqual(verdict, "NOT_COVERED")
        self.assertTrue(evidence.strip())

    def test_narrated_prose_is_never_a_verdict(self):
        """The fallback the runner used to have, pinned as refused.

        This is the defect in one place: a mode that ends its turn saying
        "TODO CORRECTO, PASS" in prose, persisting no object, must come back
        NOT_COVERED. A gate that reads prose as a verdict lets any model score
        itself by asserting it did well.
        """
        narrated = json.dumps({"verdict": "PASS", "evidence": "todo bien"})

        class _Client(_RosterClient):
            def create_creator_session(self, **kwargs):
                return "sess-1"
            def send_prompt(self, session_id, prompt, *, request_id=None):
                pass
            def creator_observation(self, session_id, *, cursor=-1):
                return {"cursor": 1, "events": [
                    {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
                    {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
                    {"type": "assistant/message", "seq": 3,
                     "data": {"text": narrated}},
                ]}
            def cancel_session(self, session_id):
                pass

        verdict, evidence = skill_gate_run._dispatch(
            _Client(), self._case(), "auditor", 5, None)
        self.assertEqual(verdict, "NOT_COVERED")
        self.assertNotIn("todo bien", evidence)

    def test_the_verdict_comes_from_the_file_the_mode_persisted(self):
        """The observation is read, not inferred from the transcript's last line:
        the same file contract the acceptance reviewer reads its actor by."""
        root = tempfile.mkdtemp(prefix="gate-case-")
        self.addCleanup(shutil.rmtree, root, True)
        case_dir = Path(root) / "case-x"
        case_dir.mkdir()
        (case_dir / "result.json").write_text(json.dumps(
            {"verdict": "FAIL", "evidence": "el modo rompió el contrato"}),
            encoding="utf-8")

        class _Client(_RosterClient):
            def create_creator_session(self, **kwargs):
                return "sess-1"
            def send_prompt(self, session_id, prompt, *, request_id=None):
                pass
            def creator_observation(self, session_id, *, cursor=-1):
                return {"cursor": 1, "events": [
                    {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
                    {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
                    # The mode narrating something else must not override what
                    # it persisted.
                    {"type": "assistant/message", "seq": 3,
                     "data": {"text": "listo, todo bien"}},
                ]}
            def cancel_session(self, session_id):
                pass

        verdict, evidence = skill_gate_run._dispatch(
            _Client(), self._case(), "auditor", 5, case_dir)
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(evidence, "el modo rompió el contrato")

    def test_every_case_gets_a_real_workspace_outside_the_framework(self):
        """The mode under test has to be able to write its answer somewhere:
        ``run_corpus`` always hands a case a directory that exists, and never
        one inside the canonical tree.

        The old dispatch passed ``None`` when no workspace was given, and
        ``create_workspace`` stringified it into the literal "None".
        """
        seen = []

        class _Client(_RosterClient):
            def create_creator_session(self, *, workspace_path=None,
                                       agent_preset=None, session_id=None):
                # Checked while the fixture still exists: the temporary
                # directory is removed when the run returns.
                if workspace_path is not None and not Path(
                        workspace_path).is_dir():
                    seen.append(f"missing:{workspace_path}")
                    return f"sess-{len(seen)}"
                seen.append(workspace_path)
                return f"sess-{len(seen)}"
            def send_prompt(self, session_id, prompt, *, request_id=None):
                pass
            def creator_observation(self, session_id, *, cursor=-1):
                return {"cursor": 1, "events": [
                    {"type": "turn/start", "seq": 1, "data": {"turn": 0}},
                    {"type": "turn/end", "seq": 2, "data": {"turn": 0}},
                ]}
            def cancel_session(self, session_id):
                pass

        class _CompatibleFixture(skill_gate_run.CompatibleEvaluator):
            def prepare(self, client, corpus, mode, root):
                self.root = root
                return {case["case_id"]: mode for case in corpus["cases"]}
            def verify_case(self, client, case, mode, path):
                return (path.parent == self.root and path.is_dir()
                        and not path.is_symlink())

        payload = skill_gate_run.run_corpus(
            _Client(), corpus_compiler.compile_corpus(LIBRARY),
            mode="auditor", candidate_digest=CAND_DIGEST,
            provider_name="fake", evaluator=_CompatibleFixture())
        self.assertEqual(len(seen), len(payload["observations"]))
        self.assertTrue(all(path is not None for path in seen), seen)
        self.assertFalse([path for path in seen
                          if str(path).startswith("missing:")], seen)
        framework = ROOT
        for path in seen:
            self.assertNotIn(str(framework), str(Path(path).parent.parent))

    def test_a_verdict_leaked_into_the_prompt_is_the_defect_not_the_case(self):
        """The scenario the mode receives carries no expected verdict, digest or
        sibling: a case that travels with its own answer measures reading."""
        sent = skill_gate_run._case_scenario(self._case())
        blob = json.dumps(sent)
        for leaked in ("expected", "corpus_digest", "candidate_digest",
                       "verdict", "provider"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, blob)
        self.assertEqual(sent["task"], "haz X")

    def test_an_environment_that_cannot_serve_the_session_api_is_not_covered(self):
        """The honest abstention the brief asks for, at the level that matters:
        ``run_corpus`` against a client that cannot serve the session API.

        A client carrying only an ``evaluator`` RPC is the shape of the broken
        contract this regression was written for -- an endpoint DSH never had.
        The run refuses before dispatching anything, as the RunnerUnavailable
        the launcher already handles as an abstention: the missing piece is
        named, no observation is claimed, and none of them is a PASS.
        """
        class _EvaluatorOnlyClient:
            """What the old contract assumed: an endpoint this release lacks."""

            def rpc(self, endpoint, request=None, timeout=30):
                raise AssertionError("endpoint inexistente")

        with self.assertRaises(skill_gate_run.RunnerUnavailable) as ctx:
            skill_gate_run.run_corpus(
                _EvaluatorOnlyClient(),
                corpus_compiler.compile_corpus(LIBRARY),
                mode="test-auditor", candidate_digest=CAND_DIGEST,
                provider_name="dsh")
        message = str(ctx.exception)
        # The exact carency this regression was written for, in the message.
        self.assertIn("list_agent_presets", message)


if __name__ == "__main__":
    unittest.main()
