"""Tests C2 Creator automation y C3 Host validator.

    python3 -B -m unittest tests.test_creator_and_validator -v
"""

import http.server
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap
import creator_client as cc
import host_validator as hv


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.workspace = self.root / "workspace"
        result = bootstrap.install(self.project, self.workspace)
        self.run_dir = Path(result["run_dir"])
        self.gen_id = result["generation_id"]

    def make_package(self, *, status="GENERATED", extra=None):
        generated = self.run_dir / "generated"
        skill = generated / "skills" / "project-auditor"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Auditor\n")
        artifacts = [{
            "path": "skills/project-auditor/SKILL.md",
            "type": "skill-entrypoint",
            "sha256": cc._digest_bytes(b"# Auditor\n"),
        }]
        manifest = {
            "schema_version": 1,
            "generation_id": self.gen_id,
            "status": status,
            "project": {"name": "project", "root_identity": "a" * 64,
                        "base_revision": "rev"},
            "creator": {"session_ref": "session", "runtime_version": "1"},
            "framework": {"revision": "framework"},
            "artifacts": artifacts,
            "required_capabilities": [],
            "forbidden_capabilities": [],
            "effective_routing_digest": "b" * 64,
            "context_policy": {"skill_entrypoint_max_bytes": 32768,
                               "support_file_max_bytes": 24576,
                               "warning_ratio": 0.9},
            "license_provenance": [],
        }
        if extra:
            manifest.update(extra)
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        return generated, manifest


class CreatorTransportTests(unittest.TestCase):
    def test_extracts_token_url_without_persisting_it(self):
        client = cc.DshLocalClient.from_console_line(
            "dsh web: http://127.0.0.1:3080/?token=runtime-only-token"
        )
        self.assertFalse(client.authenticated)
        self.assertEqual(client.base_url, "http://127.0.0.1:3080")

    def test_exchanges_token_for_cookie(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.endswith("token=runtime-only-token"):
                    self.send_response(200)
                    self.send_header("Set-Cookie", "dsh-auth-test=opaque; Path=/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"{}")
            def log_message(self, *_args):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        client = cc.DshLocalClient.from_console_line(
            f"dsh web: http://127.0.0.1:{port}/?token=runtime-only-token"
        )
        client.exchange_token()
        self.assertTrue(client.authenticated)

    def test_from_dsh_home_generates_valid_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            dsh_home = Path(tmp)
            (dsh_home / ".credentials.yaml").write_text(
                "records:\n"
                "  client-connection/browser-session:\n"
                "    payload:\n"
                "      secret: " + ("a" * 32) + "\n"
            )
            client = cc.DshLocalClient.from_dsh_home(str(dsh_home), port=3080)
            self.assertTrue(client.authenticated)
            self.assertIn("dsh-auth-", client._cookie)


class CreatorTests(Base):
    def test_prepare_builds_prompt_and_request(self):
        session = cc.CreatorSession(self.run_dir)
        result = session.prepare()
        self.assertEqual(result["generation_id"], self.gen_id)
        self.assertTrue((self.run_dir / "creator-prompt.md").is_file())
        req = json.loads((self.run_dir / "generation-request.json").read_text())
        self.assertEqual(req["prompt_version"], cc.PROMPT_VERSION)
        self.assertEqual(req["skill_selection_order"][0], "base-library")

    def test_prepare_updates_status(self):
        cc.CreatorSession(self.run_dir).prepare()
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "GENERATING")

    def test_run_creator_without_output_prepared(self):
        result = cc.run_creator(self.run_dir)
        self.assertEqual(result["result"], "PREPARED")

    def test_run_creator_with_authenticated_client_dispatches_prompt(self):
        class MockClient:
            authenticated = True
            def __init__(self):
                self.prompts = []
            def create_creator_session(self, *, cwd, agent_preset=None):
                return "mock-session-123"
            def send_prompt(self, session_id, prompt):
                self.prompts.append((session_id, prompt))
                return {"ok": True}
        mock = MockClient()
        result = cc.run_creator(self.run_dir, client=mock)
        self.assertEqual(result["result"], "PREPARED")
        self.assertEqual(result["dsh_session_id"], "mock-session-123")
        self.assertEqual(len(mock.prompts), 1)
        self.assertIn("mock-session-123", mock.prompts[0][0])

    def test_generation_output_requires_generated_status(self):
        generated, _ = self.make_package(status="ACTIVE")
        session = cc.CreatorSession(self.run_dir)
        with self.assertRaises(ValueError):
            session.verify_generation_output()

    def test_generation_output_rejects_absolute_path(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["path"] = "/etc/passwd"
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        with self.assertRaises(ValueError):
            cc.CreatorSession(self.run_dir).verify_generation_output()

    def test_retain_marks_run(self):
        session = cc.CreatorSession(self.run_dir)
        result = session.retain("missing provider")
        self.assertEqual(result["result"], "RETAINED")
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RETAINED")

    def test_prompt_contains_invariants(self):
        session = cc.CreatorSession(self.run_dir)
        session.prepare()
        prompt = (self.run_dir / "creator-prompt.md").read_text()
        self.assertIn("base-library", prompt)
        self.assertIn("no proveedores/modelos/routing nuevos", prompt.lower())
        self.assertIn("bootstrap.py accept", prompt)

    def test_all_five_prompt_types_build_successfully(self):
        run_doc = json.loads((self.run_dir / "run.json").read_text())
        proj_manifest = {"base_revision": "rev-test"}
        idx = {"entries": []}
        for ptype in cc.PROMPT_TYPES:
            prompt = cc.build_creator_prompt(
                self.run_dir, run_doc, proj_manifest, idx,
                prompt_type=ptype,
                context={"reason": "test retention", "skill_name": "test-skill"},
            )
            self.assertIn(ptype, prompt)
            self.assertIn("Invariantes", prompt)


class ValidatorTests(Base):
    def test_valid_package_ready(self):
        generated, _ = self.make_package()
        report = hv.validate_package(generated)
        self.assertTrue(report.passed)
        self.assertEqual(report.verdict, "READY_FOR_ACCEPTANCE")
        self.assertEqual(len(report.layers), 10)

    def test_bad_status_retained(self):
        generated, _ = self.make_package(status="ACTIVE")
        report = hv.validate_package(generated)
        self.assertFalse(report.passed)
        self.assertEqual(report.verdict, "RETAINED")
        self.assertFalse(report.layers["schema"]["passed"])

    def test_hash_mismatch_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["sha256"] = "0" * 64
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["manifest"]["passed"])

    def test_unsafe_path_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["path"] = "../escape"
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.passed)

    def test_capability_overlap_retained(self):
        generated, manifest = self.make_package(
            extra={"required_capabilities": ["network"],
                   "forbidden_capabilities": ["network"]}
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["capabilities"]["passed"])

    def test_portability_violation_retained(self):
        generated, manifest = self.make_package()
        skill = generated / "skills/project-auditor/SKILL.md"
        skill.write_text("import subprocess\nsubprocess.run(['x'])\n")
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["portability"]["passed"])

    def test_budget_violation_retained(self):
        generated, manifest = self.make_package()
        manifest["context_policy"]["skill_entrypoint_max_bytes"] = 1
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["context_budget"]["passed"])

    def test_host_only_artifact_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"].append({
            "path": "host-verdict.json", "type": "report",
            "sha256": "a" * 64,
        })
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["lifecycle"]["passed"])

    def test_mit_requires_notice(self):
        generated, manifest = self.make_package(
            extra={"license_provenance": [{
                "file": "skills/project-auditor/SKILL.md",
                "source": "external", "license": "MIT",
            }]}
        )
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["license"]["passed"])

    def test_write_reports(self):
        generated, _ = self.make_package()
        report = hv.validate_package(generated)
        result = hv.write_reports(report, self.run_dir)
        self.assertTrue((self.run_dir / "validation" / "summary.json").is_file())
        self.assertEqual(result["verdict"], "READY_FOR_ACCEPTANCE")


if __name__ == "__main__":
    unittest.main()
