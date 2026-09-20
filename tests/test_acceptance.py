"""Tests C5 aceptación automática Host."""
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


class FakeActors:
    def __init__(self, *, evaluator_pass=True, reviewer_pass=True):
        self.evaluator_pass = evaluator_pass
        self.reviewer_pass = reviewer_pass
        self.calls = []

    def evaluate(self, payload, _prompt):
        self.calls.append("evaluate")
        verdict = "PASS" if self.evaluator_pass else "FAIL"
        return {
            "session_id": "session-evaluator",
            "result": {
                "schema_version": 1,
                "actor": "host-evaluator",
                "generation_id": payload["generation_id"],
                "candidate_digest": payload["candidate_digest"],
                "verdict": verdict,
                "results": [{
                    "case_id": item["case_id"], "verdict": verdict,
                    "evidence": ["candidate/generation-manifest.json"],
                    "detail": "Observed against declarative contract.",
                } for item in payload["cases"]],
                "summary": "Evaluator completed all cases.",
            },
        }

    def review(self, payload, _prompt):
        self.calls.append("review")
        verdict = "PASS" if self.reviewer_pass else "FAIL"
        return {
            "session_id": "session-reviewer",
            "result": {
                "schema_version": 1,
                "actor": "host-independent-reviewer",
                "generation_id": payload["generation_id"],
                "candidate_digest": payload["candidate_digest"],
                "verdict": verdict,
                "results": [{
                    "case_id": item["case_id"], "verdict": verdict,
                    "evidence": ["candidate/generation-manifest.json"],
                    "detail": "Independent evidence review complete.",
                } for item in payload["cases"]],
                "summary": "Independent review complete.",
            },
        }


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
        self.gen_id = result["generation_id"]
        gen = self.run_dir / "generated"
        skill = gen / "skills" / "project-auditor"
        skill.mkdir(parents=True)
        content = b"# Auditor\n"
        (skill / "SKILL.md").write_bytes(content)
        plan = {
            "schema_version": 1,
            "generation_id": self.gen_id,
            "status": "GENERATED",
            "candidate_base_revision": "rev",
            "requirements": [{
                "id": "SR-1", "criterion": "Respect boundaries.",
                "evidence": "Host observations",
            }],
            "public_scenarios": [{
                "id": "PUBLIC-1", "type": "positive",
                "target": "project-auditor", "expected": "PASS",
            }],
            "holdout_families": ["prompt-injection-in-repository"],
            "gates": ["public scenarios", "hidden holdouts", "independent review"],
            "creator_limit": "Host validation only; no ACTIVE authority.",
        }
        plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
        (gen / "acceptance-plan.json").write_bytes(plan_bytes)
        manifest = {
            "schema_version": 1, "generation_id": self.gen_id,
            "status": "GENERATED",
            "project": {"name": "project", "root_identity": "a"*64, "base_revision": "rev"},
            "creator": {"session_ref": "s", "runtime_version": "1"},
            "framework": {"revision": "f"},
            "artifacts": [
                {"path": "skills/project-auditor/SKILL.md", "type": "skill-entrypoint", "sha256": hashlib.sha256(content).hexdigest()},
                {"path": "acceptance-plan.json", "type": "plan", "sha256": hashlib.sha256(plan_bytes).hexdigest()},
            ],
            "required_capabilities": [], "forbidden_capabilities": [],
            "effective_routing_digest": "b"*64,
            "context_policy": {"skill_entrypoint_max_bytes": 32768, "support_file_max_bytes": 24576, "warning_ratio": .9},
            "license_provenance": [],
        }
        (gen / "generation-manifest.json").write_text(json.dumps(manifest, indent=2))

    def test_acceptance_retains_when_evaluator_gate_fails(self):
        actors = FakeActors(evaluator_pass=False)
        result = acceptance.accept(self.run_dir, actors=actors)
        self.assertEqual(result["verdict"], "RETAINED")
        self.assertEqual(actors.calls, ["evaluate", "review"])
        self.assertTrue((self.run_dir / "acceptance" / "host-verdict.json").is_file())
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RETAINED")

    def test_all_gates_pass_emits_bound_active_verdict(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        actors = FakeActors()
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            result = acceptance.accept(self.run_dir, actors=actors)
        self.assertEqual(result["verdict"], "ACTIVE")
        validated = acceptance.validate_host_verdict(
            self.run_dir / "acceptance" / "host-verdict.json",
            self.run_dir / "generated", generation_id=self.gen_id)
        self.assertEqual(validated["verdict"], "ACTIVE")

    def test_candidate_payload_accepts_real_mode_and_contract_names(self):
        contracts = self.run_dir / "generated" / "contracts"
        modes = self.run_dir / "generated" / "modes" / "project-auditor"
        contracts.mkdir()
        modes.mkdir(parents=True)
        (contracts / "project-auditor.mode.json").write_text(
            '{"name":"project-auditor"}\n')
        (modes / "SKILL.md").write_text("# Project auditor\n")
        session = acceptance.Acceptance(self.run_dir, actors=FakeActors())
        candidate, contract_data = session._candidate_payload({})
        self.assertIn("modes/project-auditor/SKILL.md", candidate)
        self.assertIn("contracts/project-auditor.mode.json", contract_data)

    def test_evidence_and_result_artifacts_written(self):
        acceptance.accept(self.run_dir, actors=FakeActors())
        for relative in (
            "evidence-ledger.jsonl", "public-results.json",
            "holdout-results.json", "independent-review.json",
        ):
            self.assertTrue((self.run_dir / "acceptance" / relative).is_file())
        ledger = self.run_dir / "acceptance" / "evidence-ledger.jsonl"
        self.assertGreater(len(ledger.read_text().splitlines()), 0)

    def test_candidate_change_invalidates_existing_verdict(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            acceptance.accept(self.run_dir, actors=FakeActors())
        manifest = self.run_dir / "generated" / "generation-manifest.json"
        manifest.write_text(manifest.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "cambió el candidato"):
            acceptance.validate_host_verdict(
                self.run_dir / "acceptance" / "host-verdict.json",
                self.run_dir / "generated", generation_id=self.gen_id)


if __name__ == "__main__":
    unittest.main()
