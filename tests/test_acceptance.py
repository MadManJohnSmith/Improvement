"""Regression tests for deterministic, truthful Host acceptance."""
import hashlib
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acceptance
import bootstrap


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        project = root / "project"
        project.mkdir()
        (project / "main.py").write_text("x=1\n")
        result = bootstrap.install(project, root / "project-workspace")
        self.run_dir = Path(result["run_dir"])
        self.gen_id = result["generation_id"]
        gen = self.run_dir / "generated"
        capabilities = b'{"required_capabilities":[],"forbidden_capabilities":[]}\n'
        (gen / "capabilities.json").write_bytes(capabilities)
        plan = {
            "schema_version": 1, "generation_id": self.gen_id,
            "requirements": [{"id": "SR-1", "criterion": "Bounded operation",
                              "evidence": "Host static validation"}],
            "public_scenarios": [{"id": "PUBLIC-1", "type": "positive",
                                  "target": "project-auditor", "expected": "PASS"}],
            "holdout_families": ["prompt-injection-in-repository"],
            "gates": ["static validation"],
            "creator_limit": "Host validation only; no ACTIVE authority.",
        }
        plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
        (gen / "acceptance-plan.json").write_bytes(plan_bytes)
        artifacts = []
        for role in ("auditor", "continuous-repair"):
            preset_id = f"project-{role}"
            mode_dir = gen / "modes" / preset_id
            mode_dir.mkdir(parents=True)
            mode = {
                "schema_version": 1, "kind": "mode", "name": preset_id,
                "preset_id": preset_id, "role": role, "purpose": role,
                "reuse_source": "composition", "triggers": [role],
                "anti_triggers": [], "inputs": [], "reads": ["project"],
                "writes": ["mode-state"], "required_capabilities": [],
                "forbidden_capabilities": [], "invariants": ["shared state"],
                "anti_goals": [], "state_machine": {"states": ["READY"],
                    "transitions": [], "initial": "READY", "terminal": ["READY"]},
                "handoffs": [], "failure_modes": {"retries": 0,
                    "timeout_seconds": 60, "on_failure": "retain"},
                "scenarios": ["PUBLIC-1"], "provenance": {"license": "MIT"},
            }
            files = {"mode.json": json.dumps(mode, indent=2) + "\n",
                     "preset.yml": f"name: {preset_id}\n",
                     "agent.cordis.yml": "- id: persona\n  name: '@deepseek-ai/dsh-persona'\n",
                     "SKILL.md": f"# {preset_id}\n"}
            for name, text in files.items():
                (mode_dir / name).write_text(text)
                artifacts.append({"path": f"modes/{preset_id}/{name}",
                    "type": "skill-entrypoint" if name == "SKILL.md" else
                            ("mode-definition" if name == "mode.json" else
                             "mode-adapter"),
                    "sha256": hashlib.sha256(text.encode()).hexdigest()})
        artifacts += [
            {"path": "capabilities.json", "type": "manifest",
             "sha256": hashlib.sha256(capabilities).hexdigest()},
            {"path": "acceptance-plan.json", "type": "plan",
             "sha256": hashlib.sha256(plan_bytes).hexdigest()},
        ]
        manifest = {
            "schema_version": 1, "generation_id": self.gen_id, "status": "GENERATED",
            "project": {"name": "project", "root_identity": "a" * 64,
                        "base_revision": "rev"},
            "creator": {"session_ref": "creator-only", "runtime_version": "1"},
            "framework": {"revision": "f"}, "artifacts": artifacts,
            "required_capabilities": [], "forbidden_capabilities": [],
            "effective_routing_digest": "b" * 64,
            "context_policy": {"skill_entrypoint_max_bytes": 32768,
                "support_file_max_bytes": 24576, "warning_ratio": .9},
            "license_provenance": [],
        }
        (gen / "generation-manifest.json").write_text(json.dumps(manifest, indent=2))

    def test_static_failure_retains_without_dynamic_sessions(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        verdict = acceptance.accept(self.run_dir)
        self.assertEqual(verdict["verdict"], "RETAINED")
        self.assertEqual(verdict["stage"], "STATIC_VALIDATION")
        self.assertFalse((self.run_dir / "acceptance" / "host-verdict.json").exists())

    def test_valid_candidate_gets_truthful_ready_for_install(self):
        verdict = acceptance.accept(self.run_dir)
        self.assertEqual(verdict["verdict"], "READY_FOR_INSTALL")
        self.assertEqual(verdict["dynamic_evaluation"], "NOT_RUN")
        self.assertNotIn("independent_review", verdict)
        self.assertNotIn("holdout_passed", verdict)
        validated = acceptance.validate_host_verdict(
            self.run_dir / "acceptance" / "host-verdict.json",
            self.run_dir / "generated", generation_id=self.gen_id)
        self.assertEqual(validated, verdict)

    def test_acceptance_never_accepts_actor_sessions(self):
        with self.assertRaisesRegex(ValueError, "no admite evaluator/reviewer"):
            acceptance.accept(self.run_dir, actors=object())

    def test_verdict_binds_candidate_plan_summary_and_policy(self):
        acceptance.accept(self.run_dir)
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        plan = self.run_dir / "generated" / "acceptance-plan.json"
        plan.write_text(plan.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "cambió el candidato"):
            acceptance.validate_host_verdict(
                verdict_path, self.run_dir / "generated", generation_id=self.gen_id)

    def test_policy_change_invalidates_verdict(self):
        acceptance.accept(self.run_dir)
        with unittest.mock.patch.object(
                acceptance, "HOST_POLICY_VERSION", "changed"):
            with self.assertRaisesRegex(ValueError, "cambió la política Host"):
                acceptance.validate_host_verdict(
                    self.run_dir / "acceptance" / "host-verdict.json",
                    self.run_dir / "generated", generation_id=self.gen_id)

    def test_verify_acceptance_reports_truthful_fields(self):
        acceptance.accept(self.run_dir)
        report = bootstrap.verify_acceptance(
            self.run_dir.parent.parent, generation_id=self.gen_id)
        self.assertEqual(report["host_verdict"], "READY_FOR_INSTALL")
        self.assertEqual(report["stage"], "HOST_ACCEPTANCE")
        self.assertFalse(report["is_active_deployment"])


if __name__ == "__main__":
    unittest.main()
