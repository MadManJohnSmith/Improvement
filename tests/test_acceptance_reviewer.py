"""Tests del runner DSH independiente de aceptación Host."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acceptance_reviewer as ar


class FakeClient:
    authenticated = True

    def __init__(self, result_factory):
        self.result_factory = result_factory
        self.sessions = []
        self.prompts = []

    def create_creator_session(self, *, workspace_path, agent_preset="cordis"):
        sid = f"session-{len(self.sessions) + 1}"
        self.sessions.append((sid, Path(workspace_path), agent_preset))
        return sid

    def send_prompt(self, session_id, prompt):
        self.prompts.append((session_id, prompt))
        _, workspace, _ = next(row for row in self.sessions if row[0] == session_id)
        payload = json.loads((workspace / "input.json").read_text())
        result = self.result_factory(payload)
        (workspace / "result.json").write_text(json.dumps(result) + "\n")
        return {"queued": True}


class AcceptanceReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        generated = self.run_dir / "generated"
        generated.mkdir(parents=True)
        (generated / "mode.json").write_text('{"name":"x"}\n')
        self.digest = ar.tree_digest(generated)
        self.payload = {
            "generation_id": "gen-test",
            "candidate_digest": self.digest,
            "cases": [{"case_id": "A"}],
        }

    @staticmethod
    def result(payload, *, actor="host-evaluator", digest=None):
        return {
            "schema_version": 1,
            "actor": actor,
            "generation_id": payload["generation_id"],
            "candidate_digest": digest or payload["candidate_digest"],
            "verdict": "PASS",
            "results": [{"case_id": "A", "verdict": "PASS", "evidence": ["candidate/mode.json"], "detail": "ok"}],
            "summary": "Todo correcto",
        }

    def test_evaluator_binds_session_candidate_and_result(self):
        client = FakeClient(lambda payload: self.result(payload))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            observed = actors.evaluate(self.payload, "evalúa")
            workspace = Path(observed["workspace"])
            self.assertEqual(observed["result"]["candidate_digest"], self.digest)
            self.assertTrue((workspace / "candidate" / "mode.json").is_file())
            self.assertEqual(client.sessions[0][2], "standard")
            self.assertTrue(client.prompts[0][1].startswith("evalúa"))
            self.assertIn("Write exactly one final JSON object", client.prompts[0][1])
            self.assertFalse((workspace / "candidate" / "mode.json").stat().st_mode & 0o222)

    def test_evaluator_and_reviewer_use_distinct_sessions_and_workspaces(self):
        def factory(payload):
            actor = "host-evaluator" if len(client.prompts) == 1 else "host-independent-reviewer"
            return self.result(payload, actor=actor)
        client = FakeClient(factory)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            evaluator = actors.evaluate(self.payload, "eval")
            reviewer = actors.review(self.payload, "review")
        self.assertNotEqual(evaluator["session_id"], reviewer["session_id"])
        self.assertNotEqual(evaluator["workspace"], reviewer["workspace"])

    def test_tampered_digest_is_rejected(self):
        client = FakeClient(lambda payload: self.result(payload, digest="0" * 64))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "Digest"):
                actors.evaluate(self.payload, "evalúa")

    def test_wrong_actor_is_rejected(self):
        client = FakeClient(lambda payload: self.result(
            payload, actor="host-independent-reviewer"))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "Actor"):
                actors.evaluate(self.payload, "evalúa")

    def test_tree_digest_changes_with_content(self):
        before = self.digest
        (self.run_dir / "generated" / "mode.json").chmod(0o600)
        (self.run_dir / "generated" / "mode.json").write_text('{"name":"y"}\n')
        self.assertNotEqual(before, ar.tree_digest(self.run_dir / "generated"))


if __name__ == "__main__":
    unittest.main()
