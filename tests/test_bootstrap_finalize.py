"""Tests del encadenado Host automático: aceptación → activación."""
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bootstrap


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.run_dir = self.workspace / "creator-runs" / "gen-test"
        self.generated = self.run_dir / "generated"
        self.generated.mkdir(parents=True)
        (self.generated / "generation-manifest.json").write_text("{}\n")
        (self.run_dir / "acceptance").mkdir()
        (self.run_dir / "acceptance" / "request.json").write_text(
            json.dumps({"generation_id": "gen-test"}) + "\n")
        (self.run_dir / "run.json").write_text(json.dumps({
            "schema_version": 1,
            "generation_id": "gen-test",
            "status": "VALIDATING",
        }) + "\n")
        (self.run_dir / "checkpoint.json").write_text("{}\n")

    @staticmethod
    def _verdict(name):
        return {
            "schema_version": 1,
            "generation_id": "gen-test",
            "verdict": name,
            "static_passed": True,
        }

    def test_retained_pauses_without_installing(self):
        verdict = self._verdict("RETAINED")
        with unittest.mock.patch("acceptance.accept", return_value=verdict) as accept, \
             unittest.mock.patch("transaction.install") as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(result["result"], "RETAINED")
        self.assertFalse(result["is_active_deployment"])
        self.assertIn("no se instaló nada", result["message"])
        accept.assert_called_once_with(self.run_dir)
        install.assert_not_called()

    def test_active_verdict_installs_and_marks_checkpoint(self):
        verdict = self._verdict("ACTIVE")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"

        def accept(_run_dir):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict

        activation = {
            "result": "ACTIVE",
            "generation_id": "gen-test",
            "previous_generation_id": "",
        }
        with unittest.mock.patch("acceptance.accept", side_effect=accept), \
             unittest.mock.patch("transaction.install", return_value=activation) as install:
            result = bootstrap.finalize(self.workspace, "gen-test")

        self.assertEqual(result["result"], "ACTIVE")
        self.assertTrue(result["is_active_deployment"])
        install.assert_called_once_with(
            self.workspace, self.generated, "gen-test",
            host_verdict=verdict_path)
        run = json.loads((self.run_dir / "run.json").read_text())
        checkpoint = json.loads((self.run_dir / "checkpoint.json").read_text())
        self.assertEqual(run["status"], "ACTIVE")
        self.assertEqual(checkpoint["phase"], "ACTIVE")
        self.assertFalse(checkpoint["resumable"])
        self.assertEqual(checkpoint["pending_phases"], [])

    def test_existing_verdict_is_reused_without_rerunning_acceptance(self):
        verdict = self._verdict("ACTIVE")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        verdict_path.write_text(json.dumps(verdict) + "\n")
        with unittest.mock.patch("acceptance.accept") as accept, \
             unittest.mock.patch("transaction.install", return_value={
                 "result": "NO_OP", "generation_id": "gen-test",
             }) as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        accept.assert_not_called()
        install.assert_called_once()
        self.assertEqual(result["result"], "NO_OP")
        self.assertTrue(result["is_active_deployment"])

    def test_missing_acceptance_request_fails_closed(self):
        (self.run_dir / "acceptance" / "request.json").unlink()
        with self.assertRaisesRegex(ValueError, "Solicitud de aceptación ausente"):
            bootstrap.finalize(self.workspace, "gen-test")

    def test_wrong_generation_verdict_fails_closed(self):
        verdict = self._verdict("ACTIVE")
        verdict["generation_id"] = "gen-other"
        path = self.run_dir / "acceptance" / "host-verdict.json"
        path.write_text(json.dumps(verdict) + "\n")
        with self.assertRaisesRegex(ValueError, "otra generación"):
            bootstrap.finalize(self.workspace, "gen-test")


class DispatchChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "workspace" / "creator-runs" / "gen-test"
        self.run_dir.mkdir(parents=True)

    def test_generated_creator_is_finalized_by_host(self):
        result = {
            "generation_id": "gen-test",
            "message": "Run creado",
        }
        with unittest.mock.patch("creator_client.run_creator", return_value={
                "result": "GENERATED", "generation_id": "gen-test",
             }), unittest.mock.patch("bootstrap.finalize", return_value={
                "result": "ACTIVE", "generation_id": "gen-test",
             }) as finalize:
            bootstrap._dispatch_creator_chain(result, self.run_dir, False)
        finalize.assert_called_once_with(
            self.run_dir.parent.parent, generation_id="gen-test")
        self.assertEqual(result["host"]["result"], "ACTIVE")
        self.assertIn("Host: ACTIVE", result["message"])

    def test_non_generated_creator_is_not_finalized(self):
        result = {"generation_id": "gen-test", "message": "Run creado"}
        with unittest.mock.patch("creator_client.run_creator", return_value={
                "result": "PREPARED", "generation_id": "gen-test",
             }), unittest.mock.patch("bootstrap.finalize") as finalize:
            bootstrap._dispatch_creator_chain(result, self.run_dir, False)
        finalize.assert_not_called()
        self.assertNotIn("host", result)

    def test_no_finalize_escape_skips_host_chain(self):
        result = {"generation_id": "gen-test", "message": "Run creado"}
        with unittest.mock.patch("creator_client.run_creator", return_value={
                "result": "GENERATED", "generation_id": "gen-test",
             }), unittest.mock.patch("bootstrap.finalize") as finalize:
            bootstrap._dispatch_creator_chain(
                result, self.run_dir, False, finalize_host=False)
        finalize.assert_not_called()

    def test_host_failure_is_reported_and_recoverable(self):
        result = {"generation_id": "gen-test", "message": "Run creado"}
        with unittest.mock.patch("creator_client.run_creator", return_value={
                "result": "GENERATED", "generation_id": "gen-test",
             }), unittest.mock.patch("bootstrap.finalize", side_effect=ValueError("boom")):
            bootstrap._dispatch_creator_chain(result, self.run_dir, False)
        self.assertEqual(result["host"]["result"], "FINALIZATION_FAILED")
        self.assertEqual(result["host"]["error"], "boom")


if __name__ == "__main__":
    unittest.main()
