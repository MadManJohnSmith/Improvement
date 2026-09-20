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
        manifest_path = self.generated / "generation-manifest.json"
        manifest_path.write_text(json.dumps({
            "generation_id": "gen-test", "artifacts": [],
        }) + "\n")
        (self.run_dir / "acceptance").mkdir()
        (self.run_dir / "acceptance" / "request.json").write_text(
            json.dumps({
                "schema_version": 1,
                "generation_id": "gen-test",
                "manifest_digest": bootstrap._digest_file(manifest_path),
                "artifact_count": 0,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "source": "creator",
            }) + "\n")
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
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        def accept(_run_dir, launch_dsh=False):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict
        with unittest.mock.patch("acceptance.accept", side_effect=accept) as accept, \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict), \
             unittest.mock.patch("transaction.install") as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(result["result"], "RETAINED")
        self.assertFalse(result["is_active_deployment"])
        self.assertIn("no se instaló nada", result["message"])
        accept.assert_called_once_with(self.run_dir, launch_dsh=False)
        install.assert_not_called()

    def test_early_retained_is_reused_without_full_verdict_or_install(self):
        retained = {
            "schema_version": 1, "generation_id": "gen-test",
            "verdict": "RETAINED", "stage": "STATIC_VALIDATION",
            "reason": "static failed",
        }
        retained_path = self.run_dir / "acceptance" / "static-retained.json"
        retained_path.write_text(json.dumps(retained) + "\n")
        with unittest.mock.patch(
                "acceptance.validate_early_retained",
                return_value=retained) as validate_retained, \
             unittest.mock.patch("acceptance.validate_host_verdict") as validate_full, \
             unittest.mock.patch("acceptance.accept") as accept, \
             unittest.mock.patch("transaction.install") as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(result["result"], "RETAINED")
        self.assertIn("static-retained.json", result["message"])
        validate_retained.assert_called_once_with(
            retained_path, self.generated, generation_id="gen-test")
        validate_full.assert_not_called()
        accept.assert_not_called()
        install.assert_not_called()

    def test_acceptance_can_emit_early_retained_without_full_verdict(self):
        retained = {
            "schema_version": 1, "generation_id": "gen-test",
            "verdict": "RETAINED", "stage": "ACCEPTANCE_PLAN",
            "reason": "invalid plan",
        }
        retained_path = self.run_dir / "acceptance" / "static-retained.json"

        def accept(_run_dir, launch_dsh=False):
            retained_path.write_text(json.dumps(retained) + "\n")
            return retained

        with unittest.mock.patch("acceptance.accept", side_effect=accept), \
             unittest.mock.patch(
                 "acceptance.validate_early_retained",
                 return_value=retained) as validate_retained, \
             unittest.mock.patch("acceptance.validate_host_verdict") as validate_full, \
             unittest.mock.patch("transaction.install") as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(result["result"], "RETAINED")
        validate_retained.assert_called_once()
        validate_full.assert_not_called()
        install.assert_not_called()

    def test_active_verdict_installs_and_marks_checkpoint(self):
        verdict = self._verdict("READY_FOR_INSTALL")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"

        def accept(_run_dir, launch_dsh=False):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict

        activation = {
            "result": "ACTIVE",
            "generation_id": "gen-test",
            "previous_generation_id": "",
        }
        client = unittest.mock.Mock()
        client.resolved_dsh_home = Path(self.tmp.name) / "resolved-dsh-home"
        with unittest.mock.patch("acceptance.accept", side_effect=accept), \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict), \
             unittest.mock.patch("creator_client.acquire_dsh_client",
                                 return_value=(client, "test")), \
             unittest.mock.patch("transaction.install", return_value=activation) as install:
            result = bootstrap.finalize(self.workspace, "gen-test")

        self.assertEqual(result["result"], "ACTIVE")
        self.assertTrue(result["is_active_deployment"])
        install.assert_called_once_with(
            self.workspace, self.generated, "gen-test",
            host_verdict=verdict_path,
            dsh_home=client.resolved_dsh_home, client=client)
        run = json.loads((self.run_dir / "run.json").read_text())
        checkpoint = json.loads((self.run_dir / "checkpoint.json").read_text())
        self.assertEqual(run["status"], "ACTIVE")
        self.assertEqual(checkpoint["phase"], "ACTIVE")
        self.assertFalse(checkpoint["resumable"])
        self.assertEqual(checkpoint["pending_phases"], [])

    def test_existing_verdict_is_reused_without_rerunning_acceptance(self):
        verdict = self._verdict("READY_FOR_INSTALL")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        verdict_path.write_text(json.dumps(verdict) + "\n")
        client = unittest.mock.Mock()
        client.resolved_dsh_home = Path(self.tmp.name) / "resolved-dsh-home"
        with unittest.mock.patch("acceptance.accept") as accept, \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict), \
             unittest.mock.patch("creator_client.acquire_dsh_client",
                                 return_value=(client, "test")), \
             unittest.mock.patch("transaction.install", return_value={
                 "result": "NO_OP", "generation_id": "gen-test",
             }) as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        accept.assert_not_called()
        install.assert_called_once()
        self.assertEqual(result["result"], "NO_OP")
        self.assertTrue(result["is_active_deployment"])

    def test_finalize_uses_acquired_home_not_environment_home(self):
        verdict = self._verdict("READY_FOR_INSTALL")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        verdict_path.write_text(json.dumps(verdict) + "\n")
        client = unittest.mock.Mock()
        client.resolved_dsh_home = Path(self.tmp.name) / "runtime-home"
        with unittest.mock.patch.dict("os.environ", {
                "DSH_HOME": str(Path(self.tmp.name) / "wrong-home")}), \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict), \
             unittest.mock.patch("creator_client.acquire_dsh_client",
                                 return_value=(client, "runtime")), \
             unittest.mock.patch("transaction.install", return_value={
                 "result": "ACTIVE", "generation_id": "gen-test",
             }) as install:
            bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(install.call_args.kwargs["dsh_home"],
                         client.resolved_dsh_home)

    def test_finalize_rejects_client_without_resolved_home(self):
        verdict = self._verdict("READY_FOR_INSTALL")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        verdict_path.write_text(json.dumps(verdict) + "\n")
        with unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict), \
             unittest.mock.patch("creator_client.acquire_dsh_client",
                                 return_value=(object(), "legacy-home")), \
             unittest.mock.patch("transaction.install") as install:
            with self.assertRaisesRegex(ValueError, "home resuelto"):
                bootstrap.finalize(self.workspace, "gen-test")
        install.assert_not_called()

    def test_missing_acceptance_request_is_materialized_by_host(self):
        request = self.run_dir / "acceptance" / "request.json"
        request.unlink()
        verdict = self._verdict("RETAINED")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        def host_accept(_workspace, _generated, *, source="creator"):
            request.write_text(json.dumps({
                "schema_version": 1,
                "generation_id": "gen-test",
                "manifest_digest": bootstrap._digest_file(
                    self.generated / "generation-manifest.json"),
                "artifact_count": 0,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "source": source,
            }) + "\n")
            return {"result": "ACCEPT_REQUESTED"}
        def evaluate(_run_dir, launch_dsh=False):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict
        with unittest.mock.patch("bootstrap.accept", side_effect=host_accept) as accept_request, \
             unittest.mock.patch("acceptance.accept", side_effect=evaluate), \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict):
            result = bootstrap.finalize(self.workspace, "gen-test")
        accept_request.assert_called_once_with(
            self.workspace, self.generated, source="host")
        self.assertEqual(result["result"], "RETAINED")

    def test_invalid_creator_request_input_continues_to_static_retention(self):
        request = self.run_dir / "acceptance" / "request.json"
        request.unlink()
        retained = {
            "schema_version": 1, "generation_id": "gen-test",
            "verdict": "RETAINED", "stage": "STATIC_VALIDATION",
            "reason": "invalid manifest",
        }
        retained_path = self.run_dir / "acceptance" / "static-retained.json"

        def evaluate(_run_dir, launch_dsh=False):
            retained_path.write_text(json.dumps(retained) + "\n")
            return retained

        with unittest.mock.patch(
                "bootstrap.accept", side_effect=ValueError("invalid creator input")), \
             unittest.mock.patch("acceptance.accept", side_effect=evaluate), \
             unittest.mock.patch(
                 "acceptance.validate_early_retained", return_value=retained), \
             unittest.mock.patch("transaction.install") as install:
            result = bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(result["result"], "RETAINED")
        install.assert_not_called()

    def test_request_io_error_still_propagates(self):
        (self.run_dir / "acceptance" / "request.json").unlink()
        with unittest.mock.patch(
                "bootstrap.accept", side_effect=PermissionError("disk unavailable")), \
             unittest.mock.patch("acceptance.accept") as acceptance_run:
            with self.assertRaisesRegex(PermissionError, "disk unavailable"):
                bootstrap.finalize(self.workspace, "gen-test")
        acceptance_run.assert_not_called()

    def test_stale_request_after_manifest_change_is_regenerated(self):
        request_path = self.run_dir / "acceptance" / "request.json"
        old_request = json.loads(request_path.read_text())
        manifest_path = self.generated / "generation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["artifacts"].append({"path": "new", "sha256": "0" * 64})
        manifest_path.write_text(json.dumps(manifest) + "\n")
        verdict = self._verdict("RETAINED")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"

        def regenerate(_workspace, _generated, *, source="creator"):
            request = {
                "schema_version": 1, "generation_id": "gen-test",
                "manifest_digest": bootstrap._digest_file(manifest_path),
                "artifact_count": 1,
                "timestamp": "2026-01-02T00:00:00+00:00",
                "source": source,
            }
            bootstrap._replace_json(request_path, request)
            return {"result": "ACCEPT_REQUESTED"}

        def evaluate(_run_dir, launch_dsh=False):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict

        with unittest.mock.patch("bootstrap.accept", side_effect=regenerate), \
             unittest.mock.patch("acceptance.accept", side_effect=evaluate), \
             unittest.mock.patch("acceptance.validate_host_verdict",
                                 return_value=verdict):
            result = bootstrap.finalize(self.workspace, "gen-test")

        current = json.loads(request_path.read_text())
        self.assertEqual(result["result"], "RETAINED")
        self.assertNotEqual(current["manifest_digest"],
                            old_request["manifest_digest"])
        self.assertEqual(current["artifact_count"], 1)
        self.assertEqual(current["source"], "host")

    def test_request_tampering_is_not_consumed(self):
        request_path = self.run_dir / "acceptance" / "request.json"
        request = json.loads(request_path.read_text())
        request["artifact_count"] = 99
        request_path.write_text(json.dumps(request) + "\n")
        verdict = self._verdict("RETAINED")
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"

        def regenerate(_workspace, _generated, *, source="creator"):
            fresh = bootstrap._acceptance_request(
                self.run_dir, self.generated, source=source)
            bootstrap._replace_json(request_path, fresh)
            return {"result": "ACCEPT_REQUESTED"}

        def evaluate(_run_dir, launch_dsh=False):
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict

        with unittest.mock.patch("bootstrap.accept", side_effect=regenerate), \
             unittest.mock.patch("acceptance.accept", side_effect=evaluate), \
             unittest.mock.patch("acceptance.validate_host_verdict",
                                 return_value=verdict):
            bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(json.loads(request_path.read_text())["artifact_count"], 0)

    def test_request_symlink_fails_closed(self):
        request_path = self.run_dir / "acceptance" / "request.json"
        request_path.unlink()
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("{}\n")
        request_path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "enlace simbólico|symlink"):
            bootstrap.finalize(self.workspace, "gen-test")
        self.assertEqual(outside.read_text(), "{}\n")

    def test_reevaluate_deletes_only_host_derived_artifacts(self):
        acceptance_dir = self.run_dir / "acceptance"
        for name in ("host-verdict.json", "static-retained.json",
                     "public-results.json", "holdout-results.json",
                     "independent-review.json", "evidence-ledger.jsonl"):
            (acceptance_dir / name).write_text("{}\n")
        verdict = self._verdict("RETAINED")
        verdict_path = acceptance_dir / "host-verdict.json"
        def evaluate(_run_dir, launch_dsh=False):
            # Old artifacts must be absent before the new evaluator runs.
            self.assertFalse((acceptance_dir / "public-results.json").exists())
            self.assertFalse((acceptance_dir / "static-retained.json").exists())
            self.assertTrue((acceptance_dir / "request.json").exists())
            self.assertTrue((self.generated / "generation-manifest.json").exists())
            verdict_path.write_text(json.dumps(verdict) + "\n")
            return verdict
        with unittest.mock.patch("acceptance.accept", side_effect=evaluate), \
             unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict):
            result = bootstrap.finalize(
                self.workspace, "gen-test", reevaluate=True)
        self.assertEqual(result["result"], "RETAINED")

    def test_wrong_generation_verdict_fails_closed(self):
        verdict = self._verdict("READY_FOR_INSTALL")
        verdict["generation_id"] = "gen-other"
        path = self.run_dir / "acceptance" / "host-verdict.json"
        path.write_text(json.dumps(verdict) + "\n")
        with unittest.mock.patch(
                "acceptance.validate_host_verdict",
                side_effect=ValueError("host-verdict corresponde a otra generación")):
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
            self.run_dir.parent.parent, generation_id="gen-test",
            launch_dsh=False)
        self.assertEqual(result["host"]["result"], "ACTIVE")
        self.assertIn("Host: ACTIVE", result["message"])

    def test_host_rejection_ready_creator_is_finalized(self):
        result = {"generation_id": "gen-test", "message": "Run creado"}
        with unittest.mock.patch("creator_client.run_creator", return_value={
                "result": "READY_FOR_HOST_REJECTION",
                "generation_id": "gen-test", "reason": "invalid package",
             }), unittest.mock.patch("bootstrap.finalize", return_value={
                "result": "RETAINED", "generation_id": "gen-test",
             }) as finalize:
            bootstrap._dispatch_creator_chain(result, self.run_dir, False)
        finalize.assert_called_once_with(
            self.run_dir.parent.parent, generation_id="gen-test",
            launch_dsh=False)
        self.assertEqual(result["host"]["result"], "RETAINED")

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
