"""Tests C5 aceptación automática Host."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bootstrap
import acceptance


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        project = root / "project"
        project.mkdir()
        (project / "main.py").write_text("x=1\n")
        ws = root / "workspace"
        result = bootstrap.install(project, ws)
        self.run_dir = Path(result["run_dir"])
        gen = self.run_dir / "generated"
        skill = gen / "skills" / "project-auditor"
        skill.mkdir(parents=True)
        content = b"# Auditor\n"
        (skill / "SKILL.md").write_bytes(content)
        manifest = {
            "schema_version": 1, "generation_id": result["generation_id"],
            "status": "GENERATED",
            "project": {"name": "project", "root_identity": "a"*64, "base_revision": "rev"},
            "creator": {"session_ref": "s", "runtime_version": "1"},
            "framework": {"revision": "f"},
            "artifacts": [{"path": "skills/project-auditor/SKILL.md", "type": "skill-entrypoint", "sha256": __import__('hashlib').sha256(content).hexdigest()}],
            "required_capabilities": [], "forbidden_capabilities": [],
            "effective_routing_digest": "b"*64,
            "context_policy": {"skill_entrypoint_max_bytes": 32768, "support_file_max_bytes": 24576, "warning_ratio": .9},
            "license_provenance": [],
        }
        (gen / "generation-manifest.json").write_text(json.dumps(manifest, indent=2))

    def test_acceptance_retains_without_holdout_review(self):
        result = acceptance.accept(self.run_dir)
        self.assertEqual(result["verdict"], "RETAINED")
        self.assertTrue((self.run_dir / "acceptance" / "host-verdict.json").is_file())
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RETAINED")

    def test_evidence_ledger_written(self):
        acceptance.accept(self.run_dir)
        ledger = self.run_dir / "acceptance" / "evidence-ledger.jsonl"
        self.assertTrue(ledger.is_file())
        self.assertGreater(len(ledger.read_text().splitlines()), 0)


if __name__ == "__main__":
    unittest.main()
