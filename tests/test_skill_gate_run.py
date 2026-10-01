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


class _FakeClient:
    """Stands in for the DSH client: records what it was asked, answers by case."""

    def __init__(self, answers=None, error=None):
        self.answers = answers or {}
        self.error = error
        self.seen = []

    def rpc(self, endpoint, request=None, timeout=30):
        self.seen.append((endpoint, request))
        if self.error is not None:
            raise self.error
        case_id = request["scenario"]["case_id"]
        return self.answers.get(case_id)


class SkillGateRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-run-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.corpus = corpus_compiler.compile_corpus(LIBRARY)

    def _run(self, client, **kwargs):
        return skill_gate_run.run_corpus(
            client, self.corpus, mode=kwargs.pop("mode", "test-auditor"),
            candidate_digest=CAND_DIGEST, provider_name="fake",
            **kwargs)

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
        self.assertEqual(len(client.seen), len(self.corpus["cases"]))
        for endpoint, request in client.seen:
            with self.subTest(case=request["scenario"]["case_id"]):
                self.assertEqual(endpoint, "evaluator")
                sent = json.dumps(request)
                self.assertNotIn("expected", sent)
                self.assertNotIn("corpus_digest", sent)
                self.assertNotIn("verdict", sent)
                self.assertIn("task", request["scenario"])

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


if __name__ == "__main__":
    unittest.main()
