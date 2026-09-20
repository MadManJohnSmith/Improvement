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
    def __init__(self, *, evaluator_pass=True, reviewer_pass=True,
                 evaluator_decision="ALLOW"):
        self.evaluator_pass = evaluator_pass
        self.reviewer_pass = reviewer_pass
        self.evaluator_decision = evaluator_decision
        self.calls = []
        self.payloads = {}
        self.prompts = {}

    def evaluate(self, payload, prompt):
        self.calls.append("evaluate")
        self.payloads["evaluate"] = payload
        self.prompts["evaluate"] = prompt
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
                    "case_id": item["case_id"], "claim_id": "primary",
                    "verdict": verdict,
                    "decision": ("DENY" if item["case_id"].startswith("HOLDOUT-")
                                 else self.evaluator_decision),
                    "evidence": ["candidate/generation-manifest.json"],
                    "detail": "Observed against declarative contract.",
                } for item in payload["cases"]],
                "summary": "Evaluator completed all cases.",
            },
        }

    def review(self, payload, prompt):
        self.calls.append("review")
        self.payloads["review"] = payload
        self.prompts["review"] = prompt
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
        capabilities = b'{"required_capabilities":[],"forbidden_capabilities":[]}\n'
        (gen / "capabilities.json").write_bytes(capabilities)
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
                {"path": "capabilities.json", "type": "manifest", "sha256": hashlib.sha256(capabilities).hexdigest()},
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

    def test_static_failure_short_circuits_to_resumable_retained(self):
        actors = FakeActors()
        (self.run_dir / "generated" / "capabilities.json").unlink()

        result = acceptance.accept(self.run_dir, actors=actors)

        self.assertEqual(result["verdict"], "RETAINED")
        self.assertEqual(result["stage"], "STATIC_VALIDATION")
        self.assertEqual(actors.calls, [])
        retained_path = self.run_dir / "acceptance" / "static-retained.json"
        retained = acceptance.validate_early_retained(
            retained_path, self.run_dir / "generated",
            generation_id=self.gen_id)
        self.assertEqual(retained["candidate_digest"], result["candidate_digest"])
        self.assertIsNotNone(retained["manifest_digest"])
        self.assertEqual(retained["validation_summary"]["ref"],
                         "validation/summary.json")
        self.assertEqual(retained["host_policy_digest"],
                         acceptance.current_host_policy_digest())
        for relative in (
                "acceptance/host-verdict.json",
                "acceptance/public-results.json",
                "acceptance/holdout-results.json",
                "acceptance/independent-review.json",
                "acceptance/evidence-ledger.jsonl",
                "tests/public/scenarios.jsonl", "tests/holdout-spec.json"):
            self.assertFalse((self.run_dir / relative).exists(), relative)
        run = json.loads((self.run_dir / "run.json").read_text())
        checkpoint = json.loads((self.run_dir / "checkpoint.json").read_text())
        self.assertEqual(run["status"], "RETAINED")
        self.assertEqual(checkpoint["phase"], "RETAINED")
        self.assertTrue(checkpoint["resumable"])
        self.assertIn("repair", checkpoint["pending_phases"])

    def test_verify_acceptance_validates_and_exposes_static_retained(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        acceptance.accept(self.run_dir, actors=FakeActors())

        verified = bootstrap.verify_acceptance(
            self.run_dir.parent.parent, generation_id=self.gen_id)

        self.assertEqual(verified["verdict_type"], "static-retained")
        self.assertEqual(verified["host_verdict"], "RETAINED")
        self.assertEqual(verified["stage"], "STATIC_VALIDATION")
        self.assertIn("Static Host validation failed",
                      verified["reason"])
        self.assertEqual(
            set(verified["binding"]),
            {"candidate_digest", "manifest_digest", "validation_summary"})

    def test_verify_acceptance_rejects_static_retained_tampering(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        acceptance.accept(self.run_dir, actors=FakeActors())
        summary = self.run_dir / "validation" / "summary.json"
        summary.write_text(summary.read_text() + "\n")

        with self.assertRaisesRegex(ValueError, "summary no coincide"):
            bootstrap.verify_acceptance(
                self.run_dir.parent.parent, generation_id=self.gen_id)

    def test_verify_acceptance_rejects_both_verdict_forms(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        acceptance.accept(self.run_dir, actors=FakeActors())
        (self.run_dir / "acceptance" / "host-verdict.json").write_text("{}\n")

        with self.assertRaisesRegex(ValueError, "Aceptación ambigua"):
            bootstrap.verify_acceptance(
                self.run_dir.parent.parent, generation_id=self.gen_id)

    def test_validate_early_retained_rejects_layer_report_tampering(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        acceptance.accept(self.run_dir, actors=FakeActors())
        layer = self.run_dir / "validation" / "capabilities.json"
        layer_doc = json.loads(layer.read_text())
        layer_doc["candidate_digest"] = "0" * 64
        layer.write_text(json.dumps(layer_doc) + "\n")

        with self.assertRaisesRegex(ValueError, "reporte capabilities no coincide"):
            acceptance.validate_early_retained(
                self.run_dir / "acceptance" / "static-retained.json",
                self.run_dir / "generated", generation_id=self.gen_id)

    def test_malformed_static_input_retains_but_io_error_propagates(self):
        actors = FakeActors()
        manifest_path = self.run_dir / "generated" / "generation-manifest.json"
        manifest_path.write_text("{not-json\n")
        result = acceptance.accept(self.run_dir, actors=actors)
        self.assertEqual(result["stage"], "STATIC_VALIDATION")
        self.assertEqual(actors.calls, [])

        other_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(other_tmp.cleanup)
        other = Path(other_tmp.name) / "run"
        (other / "generated").mkdir(parents=True)
        (other / "acceptance").mkdir()
        (other / "run.json").write_text(json.dumps({
            "generation_id": "gen-io", "status": "VALIDATING"}) + "\n")
        (other / "checkpoint.json").write_text("{}\n")
        with unittest.mock.patch.object(
                acceptance.host_validator, "validate_package",
                side_effect=PermissionError("host storage unavailable")):
            with self.assertRaisesRegex(PermissionError, "storage unavailable"):
                acceptance.accept(other, actors=actors)
        self.assertFalse((other / "acceptance" /
                          "static-retained.json").exists())

    def test_invalid_creator_plan_after_static_pass_retains_without_actors(self):
        plan_path = self.run_dir / "generated" / "acceptance-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["requirements"][0]["criterion"] = "   "
        plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
        plan_path.write_bytes(plan_bytes)
        manifest_path = self.run_dir / "generated" / "generation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        next(item for item in manifest["artifacts"]
             if item["path"] == "acceptance-plan.json")["sha256"] = (
                 hashlib.sha256(plan_bytes).hexdigest())
        manifest_path.write_text(json.dumps(manifest, indent=2))
        actors = FakeActors()

        result = acceptance.accept(self.run_dir, actors=actors)

        self.assertEqual(result["verdict"], "RETAINED")
        self.assertEqual(result["stage"], "STATIC_VALIDATION")
        self.assertIn("Static Host validation failed", result["reason"])
        self.assertEqual(actors.calls, [])
        self.assertTrue((self.run_dir / "acceptance" /
                         "static-retained.json").is_file())
        self.assertFalse((self.run_dir / "tests" / "public" /
                          "scenarios.jsonl").exists())
        self.assertFalse((self.run_dir / "tests" /
                          "holdout-spec.json").exists())
        self.assertFalse((self.run_dir / "acceptance" /
                          "host-verdict.json").exists())

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
        self.assertEqual(validated["host_policy_digest"],
                         acceptance.current_host_policy_digest())

    def test_host_verdict_rejects_tampered_policy_digest(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            acceptance.accept(self.run_dir, actors=FakeActors())
        verdict_path = self.run_dir / "acceptance" / "host-verdict.json"
        verdict = json.loads(verdict_path.read_text())
        verdict["host_policy_digest"] = "0" * 64
        verdict_path.write_text(json.dumps(verdict) + "\n")

        with self.assertRaisesRegex(ValueError, "cambió la política Host"):
            acceptance.validate_host_verdict(
                verdict_path, self.run_dir / "generated",
                generation_id=self.gen_id)

    def test_host_verdict_is_stale_when_current_policy_changes(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            acceptance.accept(self.run_dir, actors=FakeActors())

        with unittest.mock.patch.object(
                acceptance, "HOST_POLICY_VERSION",
                acceptance.HOST_POLICY_VERSION + "-changed"):
            with self.assertRaisesRegex(ValueError, "cambió la política Host"):
                acceptance.validate_host_verdict(
                    self.run_dir / "acceptance" / "host-verdict.json",
                    self.run_dir / "generated", generation_id=self.gen_id)

    def test_static_retained_is_stale_when_current_policy_changes(self):
        (self.run_dir / "generated" / "capabilities.json").unlink()
        acceptance.accept(self.run_dir, actors=FakeActors())

        with unittest.mock.patch.object(
                acceptance, "HOST_POLICY_VERSION",
                acceptance.HOST_POLICY_VERSION + "-changed"):
            with self.assertRaisesRegex(ValueError, "cambió la política Host"):
                acceptance.validate_early_retained(
                    self.run_dir / "acceptance" / "static-retained.json",
                    self.run_dir / "generated", generation_id=self.gen_id)

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

    def test_holdout_grading_uses_decision_not_free_verdict(self):
        session = acceptance.Acceptance(self.run_dir, actors=FakeActors())
        case_id = "HOLDOUT-test"
        materialized = {
            "public_cases": [],
            "holdout_cases": [{"case_id": case_id, "family": "test"}],
            "holdout_oracles": {case_id: {
                "expected_decision": "DENY",
                "required_behavior": "private canary",
            }},
        }
        for decision, verdict, expected in (
                ("DENY", "FAIL", True),
                ("ALLOW", "PASS", False),
                ("UNRESOLVED", "PASS", False)):
            with self.subTest(decision=decision, verdict=verdict):
                session.results = []
                graded = session._grade(materialized, [{
                    "case_id": case_id,
                    "claim_id": "primary",
                    "verdict": verdict,
                    "decision": decision,
                    "evidence": "candidate/generation-manifest.json",
                    "detail": "Structured observation.",
                }])
                self.assertEqual(graded[2], expected)
                self.assertEqual(graded[3][0]["passed"], expected)

    def test_public_grading_separates_expected_behavior_from_evaluator_quality(self):
        session = acceptance.Acceptance(self.run_dir, actors=FakeActors())
        base_case = {
            "schema_version": 1, "scenario_id": "PUBLIC-gate",
            "type": "positive", "description": "Host public gate",
            "input": {"evaluated_action": "perform the bounded action"},
            "sr_links": ["SR-1"],
        }
        base_observed = {
            "case_id": "PUBLIC-gate", "claim_id": "primary",
            "verdict": "PASS", "decision": "ALLOW", "evidence": "public/ref",
            "detail": "Evaluator rationale.",
        }
        cases = (
            # BLOCKED and NOT_COVERED are expected scenario behaviors. The
            # evaluator still reports PASS when the candidate represents them.
            ("BLOCKED", "DENY", "PASS", "DENY", True),
            ("NOT_COVERED", "DENY", "PASS", "DENY", True),
            # A contradictory structured decision fails despite quality PASS.
            ("BLOCKED", "DENY", "PASS", "ALLOW", False),
            # Evaluator FAIL always fails, even with the Host decision.
            ("NOT_COVERED", "DENY", "FAIL", "DENY", False),
            # Preserve the historical fail-closed public expected policy.
            ("FAIL", "DENY", "PASS", "DENY", False),
            ("PASS", "ALLOW", "PASS", "ALLOW", True),
        )
        for (expected_behavior, expected_decision, evaluator_verdict,
             observed_decision, passes) in cases:
            with self.subTest(expected_behavior=expected_behavior,
                              expected_decision=expected_decision,
                              evaluator_verdict=evaluator_verdict,
                              observed_decision=observed_decision):
                materialized = {
                    "public_cases": [base_case | {
                        "expected": {"verdict": expected_behavior},
                    }],
                    "public_expected_decisions": {
                        "PUBLIC-gate": expected_decision,
                    },
                    "holdout_cases": [], "holdout_oracles": {},
                }
                session.results = []
                graded = session._grade(materialized, [base_observed | {
                    "verdict": evaluator_verdict,
                    "decision": observed_decision,
                }])
                self.assertEqual(graded[0], passes)
                self.assertEqual(graded[1][0]["passed"], passes)
                self.assertEqual(graded[1][0]["expected"], expected_behavior)
                self.assertEqual(graded[1][0]["observed"], evaluator_verdict)
                self.assertEqual(
                    graded[1][0]["expected_decision"], expected_decision)

    def test_capability_denial_rejects_contradictory_allow(self):
        session = acceptance.Acceptance(self.run_dir, actors=FakeActors())
        case = {
            "schema_version": 1, "scenario_id": "PUBLIC-denial",
            "type": "capability-denial", "description": "Host denial case",
            "input": {"evaluated_action": "use canonical_write"},
            "expected": {"verdict": "PASS"}, "sr_links": ["SR-1"],
        }
        materialized = {
            "public_cases": [case],
            "public_expected_decisions": {"PUBLIC-denial": "DENY"},
            "holdout_cases": [], "holdout_oracles": {},
        }
        observed = {
            "case_id": "PUBLIC-denial", "claim_id": "primary",
            "verdict": "PASS", "decision": "ALLOW", "evidence": "public/ref",
            "detail": "Contradictory evaluator rationale.",
        }
        graded = session._grade(materialized, [observed])
        self.assertFalse(graded[0])
        self.assertFalse(graded[1][0]["passed"])

    def test_public_detail_is_canonical_and_discards_evaluator_overclaim(self):
        class OverclaimActors(FakeActors):
            def evaluate(inner, payload, prompt):
                observation = super(OverclaimActors, inner).evaluate(payload, prompt)
                observation["result"]["results"][0]["detail"] = (
                    "FAKE_OVERCLAIM: candidate permits unrelated network deletion")
                return observation

        actors = OverclaimActors(evaluator_decision="ALLOW")
        acceptance.accept(self.run_dir, actors=actors)
        public = json.loads((self.run_dir / "acceptance" /
                             "public-results.json").read_text())
        detail = public["results"][0]["detail"]
        self.assertNotIn("FAKE_OVERCLAIM", detail)
        self.assertIn("evaluated_claim", detail)
        self.assertIn("evaluator decision=ALLOW", detail)
        self.assertIn("evaluator verdict=PASS", detail)
        self.assertIn("bounded fixture", detail)

    def test_misleading_capability_denial_id_reviews_canonical_write_subject(self):
        plan_path = self.run_dir / "generated" / "acceptance-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["public_scenarios"] = [{
            "id": "PUBLIC-network-delete-allowed",
            "type": "capability-denial",
            "target": "project-auditor",
            "expected": "PASS",
        }]
        plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
        plan_path.write_bytes(plan_bytes)
        manifest_path = self.run_dir / "generated" / "generation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        next(item for item in manifest["artifacts"]
             if item["path"] == "acceptance-plan.json")["sha256"] = (
                 hashlib.sha256(plan_bytes).hexdigest())
        manifest_path.write_text(json.dumps(manifest, indent=2))

        actors = FakeActors(evaluator_decision="DENY")
        acceptance.accept(self.run_dir, actors=actors)
        prompt = actors.prompts["review"]
        self.assertIn('"capability": "canonical_write"', prompt)
        self.assertIn('"evaluated_action": "use the canonical_write capability"',
                      prompt)
        self.assertIn("PUBLIC-network-delete-allowed", prompt)
        self.assertIn("Never infer case semantics from case_id", prompt)

    def test_evidence_and_result_artifacts_written_without_private_oracle(self):
        acceptance.accept(self.run_dir, actors=FakeActors())
        for relative in (
            "evidence-ledger.jsonl", "public-results.json",
            "holdout-results.json", "independent-review.json",
        ):
            self.assertTrue((self.run_dir / "acceptance" / relative).is_file())
        ledger = self.run_dir / "acceptance" / "evidence-ledger.jsonl"
        self.assertGreater(len(ledger.read_text().splitlines()), 0)
        public = (self.run_dir / "acceptance" / "public-results.json").read_text()
        holdout = (self.run_dir / "acceptance" / "holdout-results.json").read_text()
        review = (self.run_dir / "acceptance" / "independent-review.json").read_text()
        ledger_text = ledger.read_text()
        private_visible = holdout + ledger_text
        self.assertNotIn("expected_decision", private_visible)
        self.assertNotIn("required_behavior", private_visible)
        self.assertNotIn('"decision"', private_visible)
        public_doc = json.loads(public)
        self.assertEqual(public_doc["results"][0]["decision"], "ALLOW")
        self.assertEqual(public_doc["results"][0]["expected_decision"], "ALLOW")

        holdout_doc = json.loads(holdout)
        self.assertEqual(set(holdout_doc["results"][0]), {
            "case_id", "family", "passed", "evidence", "detail",
        })
        ledger_rows = [json.loads(line) for line in ledger_text.splitlines()]
        self.assertTrue(all("decision" not in row for row in ledger_rows))

    def test_reviewer_receives_only_public_case_ids_and_summary(self):
        actors = FakeActors()
        acceptance.accept(self.run_dir, actors=actors)
        reviewer_payload = actors.payloads["review"]
        reviewer_prompt = actors.prompts["review"]
        serialized_review_input = json.dumps(
            reviewer_payload, sort_keys=True) + reviewer_prompt
        self.assertEqual(len(reviewer_payload["cases"]), 1)
        reviewer_case = reviewer_payload["cases"][0]
        self.assertEqual(set(reviewer_case), {
            "case_id", "claim_id", "subject", "input", "decision",
            "expected_public_behavior", "expected_decision", "passed", "evidence",
        })
        self.assertEqual(reviewer_case["case_id"], "PUBLIC-1")
        self.assertEqual(reviewer_case["claim_id"], "primary")
        self.assertEqual(reviewer_case["subject"]["field"], "evaluated_claim")
        self.assertEqual(reviewer_case["decision"], "ALLOW")
        self.assertEqual(reviewer_case["expected_decision"], "ALLOW")
        self.assertTrue(reviewer_case["passed"])
        self.assertNotIn("detail", reviewer_case)
        self.assertNotIn("HOLDOUT-", serialized_review_input)
        self.assertNotIn("holdout-results", serialized_review_input)
        self.assertNotIn("holdout_oracles", serialized_review_input)
        self.assertNotIn("required_behavior", serialized_review_input)

    def test_verify_acceptance_validates_and_exposes_host_verdict(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            acceptance.accept(self.run_dir, actors=FakeActors())

        verified = bootstrap.verify_acceptance(
            self.run_dir.parent.parent, generation_id=self.gen_id)

        self.assertEqual(verified["verdict_type"], "host-verdict")
        self.assertEqual(verified["host_verdict"], "ACTIVE")
        self.assertEqual(verified["stage"], "HOST_ACCEPTANCE")
        self.assertIsNone(verified["reason"])
        self.assertEqual(set(verified["binding"]), {
            "candidate_digest", "manifest_digest", "public_results_digest",
            "holdout_results_digest", "review_digest", "host_policy_digest",
        })

    def test_verify_acceptance_rejects_host_verdict_tampering(self):
        class PassingReport:
            passed = True
            verdict = "READY_FOR_ACCEPTANCE"
        with unittest.mock.patch.object(
                acceptance.Acceptance, "static_validation",
                return_value=PassingReport()):
            acceptance.accept(self.run_dir, actors=FakeActors())
        public = self.run_dir / "acceptance" / "public-results.json"
        public.write_text(public.read_text() + "\n")

        with self.assertRaisesRegex(ValueError, "public_results_digest"):
            bootstrap.verify_acceptance(
                self.run_dir.parent.parent, generation_id=self.gen_id)

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
