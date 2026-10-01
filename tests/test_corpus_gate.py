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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus_compiler
import skill_gate

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


if __name__ == "__main__":
    unittest.main()
