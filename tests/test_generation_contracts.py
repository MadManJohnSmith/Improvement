"""Tests de contratos generacionales — corpus positivo y negativo C0.

Valida que el validador de contratos acepta documentos válidos sin DSH
y rechaza cerrado cada caso negativo sin escribir nada.

    python3 -B -m unittest tests.test_generation_contracts -v
"""

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generation_contracts as gc

# ---------------------------------------------------------------------------
# Golden fixture helpers
# ---------------------------------------------------------------------------

_FAKE_SHA = "a" * 64
_FAKE_SHA_B = "b" * 64
_NOW = "2026-09-16T10:00:00Z"


def _golden_run():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "status": "CREATED",
        "created_at": _NOW,
        "project": {"name": "TestProject", "root_identity": _FAKE_SHA},
        "framework_revision": "abc123",
    }


def _golden_generation_manifest():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "status": "GENERATED",
        "project": {
            "name": "TestProject",
            "root_identity": _FAKE_SHA,
            "base_revision": "rev-001",
        },
        "creator": {
            "session_ref": "sess-001",
            "runtime_version": "1.0.0",
        },
        "framework": {"revision": "abc123"},
        "artifacts": [
            {
                "path": "generation-manifest.json",
                "type": "manifest",
                "sha256": _FAKE_SHA,
            },
            {
                "path": "skills/TestProject-auditor/SKILL.md",
                "type": "skill-entrypoint",
                "sha256": _FAKE_SHA_B,
                "size_bytes": 1024,
            },
        ],
        "required_capabilities": ["product_read"],
        "forbidden_capabilities": ["network"],
        "effective_routing_digest": _FAKE_SHA,
        "context_policy": {
            "skill_entrypoint_max_bytes": 32768,
            "support_file_max_bytes": 24576,
            "warning_ratio": 0.9,
        },
        "license_provenance": [],
    }


def _golden_project_manifest():
    return {
        "schema_version": 1,
        "name": "TestProject",
        "root_identity": _FAKE_SHA,
        "base_revision": "rev-001",
        "inventory": {
            "total_files": 42,
            "total_bytes": 100000,
            "languages": ["python"],
            "areas": [
                {"name": "src", "path": "src/", "file_count": 30},
            ],
        },
        "authority": {"holder": "user", "source": "declared"},
    }


def _golden_instructions_index():
    return {
        "schema_version": 1,
        "entries": [
            {
                "path": "AGENTS.md",
                "scope": "workspace",
                "precedence": 10,
                "sha256": _FAKE_SHA,
                "sections": ["rules"],
                "facts": ["Python 3.14"],
                "constraints": ["no external deps"],
                "unknowns": [],
                "conflicts": [],
            },
        ],
    }


def _golden_capabilities():
    return {
        "schema_version": 1,
        "capability_id": "cap-001",
        "session_id": "sess-001",
        "project": "TestProject",
        "executor": "creator",
        "roots": {
            "product_read": ["/project"],
            "framework_execute": ["/framework"],
            "workspace_write": ["/workspace"],
        },
        "scope": ["audit", "repair"],
    }


def _golden_scenario():
    return {
        "schema_version": 1,
        "scenario_id": "SC-001",
        "type": "positive",
        "description": "Valid audit cycle completes successfully",
        "input": {"project": "TestProject", "mode": "auditor"},
        "expected": {"verdict": "PASS"},
        "sr_links": ["SR-1", "SR-2"],
    }


def _golden_handoff():
    return {
        "schema_version": 1,
        "type": "creator.generation.complete",
        "run_id": "gen-001",
        "candidate_digest": _FAKE_SHA,
        "source_actor": "creator",
        "target_actor": "host",
        "reason": "Generation complete, requesting validation",
        "attempt": 1,
        "timestamp": _NOW,
    }


def _golden_drift():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "comparison_points": {
            "project_base": "rev-001",
            "accepted_generation": "gen-000",
        },
        "entries": [
            {
                "path": "skills/TestProject-auditor/SKILL.md",
                "status": "CURRENT",
                "source": "installed-vs-accepted",
            },
        ],
    }


def _golden_backup():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "timestamp": _NOW,
        "previous_generation_id": "gen-000",
        "entries": [
            {
                "path": "skills/old-skill/SKILL.md",
                "sha256": _FAKE_SHA,
                "disposition": "managed-modified",
                "backup_path": "previous-skills/old-skill/SKILL.md",
                "size_bytes": 512,
            },
        ],
        "hashes_digest": _FAKE_SHA,
        "verified": True,
    }


def _golden_promotion():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "status": "PROMOTED",
        "acceptance_record": {
            "verdict": "ACCEPTED",
            "timestamp": _NOW,
            "evidence_refs": ["evidence/acceptance.json"],
        },
    }


def _golden_rollback():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "rolled_back_to": "gen-000",
        "reason": "Acceptance failed on holdout scenarios",
        "timestamp": _NOW,
        "verification": {
            "hashes_match": True,
            "files_restored": 5,
            "files_removed": 3,
        },
    }


def _golden_library():
    return {
        "schema_version": 1,
        "base_skills": [
            {
                "name": "project-onboarding",
                "purpose": "Incorporate or recognize a project for audit/repair",
                "applicability": "Any project needing initial setup",
                "invariants": ["Never modifies product code"],
                "limits": ["Single project per invocation"],
                "scenarios": ["SC-010"],
                "provenance": {"license": "proprietary", "source": "internal"},
            },
        ],
        "catalog_patterns": [
            {
                "name": "python-backend-auditor",
                "domain": "python-backend",
                "purpose": "Audit patterns for Python backend projects",
                "applicability": "Projects with Python backend code",
                "activation_criteria": [
                    "Project contains Python backend packages or services",
                ],
                "invariants": ["Read-only access to product"],
                "scenarios": ["SC-020"],
                "provenance": {"license": "proprietary", "source": "internal"},
            },
        ],
        "composition_rules": {
            "allowed": True,
            "constraints": [
                "Composed skills must not have conflicting capabilities",
                "Maximum two skills in a composition",
            ],
            "max_composed": 3,
        },
        "override_rules": {
            "allowed_slots": ["triggers", "anti_triggers", "stop_conditions"],
            "forbidden_slots": [
                "invariants", "required_capabilities",
                "forbidden_capabilities", "provenance",
            ],
            "requires_justification": True,
        },
        "transfer_rules": {
            "requires_acceptance": True,
            "acceptance_scope": "full",
            "source_tracking": True,
        },
        "extension_rules": {
            "requires_justification": True,
            "must_demonstrate_no_prior_layer": True,
            "fallback_on_failure": "RETAINED",
        },
    }


def _golden_mode_contract():
    return {
        "schema_version": 1,
        "name": "TestProject-auditor",
        "purpose": "Audit TestProject for defects",
        "reuse_source": "base-library",
        "triggers": ["audit request", "scheduled audit"],
        "anti_triggers": ["repair in progress"],
        "inputs": ["project source", "instructions index"],
        "reads": ["product/"],
        "writes": [],
        "required_capabilities": ["product_read"],
        "forbidden_capabilities": ["product_write", "network"],
        "invariants": ["Never writes to product", "Max two attempts per unit"],
        "anti_goals": ["Do not modify source code"],
        "state_machine": {
            "states": ["READY", "AUDITING", "COMPLETE", "FAILED"],
            "transitions": [
                {"from": "READY", "to": "AUDITING", "trigger": "start"},
                {"from": "AUDITING", "to": "COMPLETE", "trigger": "pass"},
                {"from": "AUDITING", "to": "FAILED", "trigger": "error"},
            ],
            "initial": "READY",
            "terminal": ["COMPLETE", "FAILED"],
        },
        "handoffs": [
            {"target": "TestProject-continuous-repair", "condition": "defects found"},
        ],
        "failure_modes": {
            "retries": 1,
            "timeout_seconds": 300,
            "on_failure": "retain",
        },
        "scenarios": ["SC-001", "SC-002"],
        "provenance": {"license": "proprietary"},
    }


def _golden_skill_contract():
    return {
        "schema_version": 1,
        "name": "TestProject-auditor",
        "motive": "Recurring audit procedure for TestProject",
        "domain": ["python-backend"],
        "reuse_source": "base-library",
        "inputs": ["project source"],
        "outputs": ["audit report"],
        "required_capabilities": ["product_read"],
        "forbidden_capabilities": ["product_write"],
        "files": [
            {"path": "SKILL.md", "type": "entrypoint", "max_bytes": 32768},
            {"path": "modes/full.md", "type": "mode"},
        ],
        "behavior_test": "SC-001",
        "provenance": {"license": "proprietary"},
    }


def _golden_discovery():
    return {
        "schema_version": 1,
        "project": "TestProject",
        "claims": [
            {
                "source": "src/main.py",
                "hash": _FAKE_SHA,
                "location": "src/main.py:1",
                "state": "OBSERVED",
                "confidence": "high",
            }
        ],
    }


def _golden_design():
    return {
        "schema_version": 1,
        "project": "TestProject",
        "strategy": {
            "selection_order": ["base-library", "specialized-catalog"],
            "modes": ["TestProject-auditor", "TestProject-continuous-repair"],
        },
        "decisions": [
            {
                "id": "D-001",
                "subject": "use standard library",
                "resolution": "INFER",
                "justification": "evidenced in codebase",
            }
        ],
    }


def _golden_tests_spec():
    return {
        "schema_version": 1,
        "generation_id": "gen-001",
        "families": ["boundary", "cycle"],
        "coverage_matrix": {
            "total_scenarios": 5,
            "covered_requirements": ["SR-1", "SR-2"],
        },
    }


# ===========================================================================
# Positive corpus: every golden fixture passes validation
# ===========================================================================


class TestPositiveCorpus(unittest.TestCase):
    """Corpus positivo: todo documento dorado se acepta sin DSH."""

    def test_run_golden(self):
        gc.validate("run", _golden_run())

    def test_run_all_statuses(self):
        for s in gc.RUN_STATUSES:
            doc = _golden_run()
            doc["status"] = s
            gc.validate("run", doc)

    def test_run_with_optional_fields(self):
        doc = _golden_run()
        doc["updated_at"] = _NOW
        doc["templates_revision"] = "tmpl-001"
        doc["budget"] = {
            "max_attempts": 3,
            "max_tokens": 100000,
            "max_seconds": 600,
            "max_cost_usd": 5.0,
        }
        doc["directories"] = {
            "inputs": "inputs",
            "discovery": "discovery",
            "generated": "generated",
        }
        gc.validate("run", doc)

    def test_generation_manifest_golden(self):
        gc.validate("generation-manifest", _golden_generation_manifest())

    def test_generation_manifest_with_provenance(self):
        doc = _golden_generation_manifest()
        doc["license_provenance"] = [
            {
                "file": "skills/TestProject-auditor/SKILL.md",
                "source": "jsmastery-pro/skills",
                "commit": "43b69e44c9ca905fe3a3418ccdf4102255e20d40",
                "license": "MIT",
            },
        ]
        gc.validate("generation-manifest", doc)

    def test_generation_manifest_with_hot_paths(self):
        doc = _golden_generation_manifest()
        doc["context_policy"]["hot_paths"] = {
            "skills/TestProject-auditor/": 65536,
        }
        gc.validate("generation-manifest", doc)

    def test_project_manifest_golden(self):
        gc.validate("project-manifest", _golden_project_manifest())

    def test_project_manifest_with_hashes(self):
        doc = _golden_project_manifest()
        doc["hashes"] = {"src/main.py": _FAKE_SHA}
        gc.validate("project-manifest", doc)

    def test_instructions_index_golden(self):
        gc.validate("instructions-index", _golden_instructions_index())

    def test_capabilities_golden(self):
        gc.validate("capabilities", _golden_capabilities())

    def test_capabilities_with_forbidden(self):
        doc = _golden_capabilities()
        doc["required_capabilities"] = ["product_read"]
        doc["forbidden_capabilities"] = ["network"]
        gc.validate("capabilities", doc)

    def test_scenario_golden(self):
        gc.validate("scenario", _golden_scenario())

    def test_scenario_all_types(self):
        for t in gc.SCENARIO_TYPES:
            doc = _golden_scenario()
            doc["type"] = t
            gc.validate("scenario", doc)

    def test_scenario_with_optional_fields(self):
        doc = _golden_scenario()
        doc["target_mode"] = "TestProject-auditor"
        doc["target_skill"] = "TestProject-auditor"
        doc["holdout_family"] = "boundary"
        doc["verification_state"] = "UNVERIFIED"
        gc.validate("scenario", doc)

    def test_handoff_golden(self):
        gc.validate("handoff", _golden_handoff())

    def test_handoff_all_types(self):
        for t in gc.HANDOFF_TYPES:
            doc = _golden_handoff()
            doc["type"] = t
            gc.validate("handoff", doc)

    def test_drift_golden(self):
        gc.validate("drift", _golden_drift())

    def test_drift_all_statuses(self):
        for s in gc.DRIFT_STATUSES:
            doc = _golden_drift()
            doc["entries"][0]["status"] = s
            gc.validate("drift", doc)

    def test_backup_golden(self):
        gc.validate("backup", _golden_backup())

    def test_promotion_golden(self):
        gc.validate("promotion", _golden_promotion())

    def test_rollback_golden(self):
        gc.validate("rollback", _golden_rollback())

    def test_library_golden(self):
        gc.validate("library", _golden_library())

    def test_mode_contract_golden(self):
        gc.validate("mode-contract", _golden_mode_contract())

    def test_skill_contract_golden(self):
        gc.validate("skill-contract", _golden_skill_contract())

    def test_discovery_golden(self):
        gc.validate("discovery", _golden_discovery())

    def test_design_golden(self):
        gc.validate("design", _golden_design())

    def test_tests_spec_golden(self):
        gc.validate("tests-spec", _golden_tests_spec())


# ===========================================================================
# Negative corpus: every invalid document fails closed without writing
# ===========================================================================


class TestNegativeCorpus(unittest.TestCase):
    """Corpus negativo: cada caso inválido falla cerrado sin escritura."""

    # -- 1. Path traversal --------------------------------------------------

    def test_path_traversal_in_artifact(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["path"] = "../etc/passwd"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_path_traversal_embedded(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["path"] = "skills/../../../etc/shadow"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_absolute_path_in_artifact(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["path"] = "/etc/passwd"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_double_slash_in_path(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["path"] = "skills//SKILL.md"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_path_safety_check_null_byte(self):
        with self.assertRaises(gc.ContractError):
            gc.check_path_safety("skills/\x00evil")

    def test_path_safety_check_traversal(self):
        with self.assertRaises(gc.ContractError):
            gc.check_path_safety("../escape")

    # -- 2. Symlink ----------------------------------------------------------

    def test_symlink_in_generated_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            real = gen / "real.json"
            real.write_text("{}")
            link = gen / "link.json"
            link.symlink_to(real)

            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "real.json", "type": "manifest",
                 "sha256": gc.compute_file_sha256(real)},
                {"path": "link.json", "type": "manifest",
                 "sha256": gc.compute_file_sha256(real)},
            ]
            with self.assertRaises(gc.ContractError) as ctx:
                gc.verify_manifest_hashes(manifest, str(gen))
            self.assertIn("symlink", str(ctx.exception))

    def test_symlink_rejection_in_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "dir"
            d.mkdir()
            target = d / "target.txt"
            target.write_text("data")
            link = d / "link.txt"
            link.symlink_to(target)
            with self.assertRaises(gc.ContractError):
                gc.check_no_symlinks(str(d))

    # -- 3. Hash stale / mismatch -------------------------------------------

    def test_stale_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            f = gen / "SKILL.md"
            f.write_text("# Real content")
            actual = gc.compute_file_sha256(f)

            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "SKILL.md", "type": "skill-entrypoint",
                 "sha256": "0" * 64},
            ]
            mismatches = gc.verify_manifest_hashes(manifest, str(gen))
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0][0], "SKILL.md")
            self.assertEqual(mismatches[0][1], "0" * 64)
            self.assertEqual(mismatches[0][2], actual)

    # -- 4. Manifest incompleto (missing file) ------------------------------

    def test_manifest_references_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "nonexistent.md", "type": "manifest",
                 "sha256": _FAKE_SHA},
            ]
            with self.assertRaises(gc.ContractError) as ctx:
                gc.verify_manifest_hashes(manifest, str(gen))
            self.assertIn("missing", str(ctx.exception))

    def test_unmanifested_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            declared = gen / "declared.md"
            declared.write_text("ok")
            extra = gen / "extra.md"
            extra.write_text("sneaky")

            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "declared.md", "type": "manifest",
                 "sha256": gc.compute_file_sha256(declared)},
            ]
            with self.assertRaises(gc.ContractError) as ctx:
                gc.verify_manifest_hashes(manifest, str(gen))
            self.assertIn("unmanifested", str(ctx.exception))

    # -- 5. New routing (unknown routing digest) ----------------------------

    def test_empty_routing_digest(self):
        doc = _golden_generation_manifest()
        doc["effective_routing_digest"] = ""
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- 6. New provider (unknown status) ------------------------------------

    def test_unknown_run_status(self):
        doc = _golden_run()
        doc["status"] = "MAGIC_NEW_STATUS"
        with self.assertRaises(gc.ContractError):
            gc.validate("run", doc)

    # -- 7. Orphan skill (duplicate artifact path) --------------------------

    def test_duplicate_artifact_path(self):
        doc = _golden_generation_manifest()
        dup = copy.deepcopy(doc["artifacts"][0])
        doc["artifacts"].append(dup)
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("generation-manifest", doc)
        self.assertIn("duplicate", str(ctx.exception))

    # -- 8. Load cycle (detected via state machine) -------------------------

    def test_empty_state_machine_states(self):
        doc = _golden_mode_contract()
        doc["state_machine"]["states"] = []
        with self.assertRaises(gc.ContractError):
            gc.validate("mode-contract", doc)

    # -- 9. Unresolved decision (empty required fields) ---------------------

    def test_missing_generation_id(self):
        doc = _golden_generation_manifest()
        del doc["generation_id"]
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_empty_generation_id(self):
        doc = _golden_generation_manifest()
        doc["generation_id"] = ""
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- 10. Extension libre when base applies --------------------------------

    def test_extension_without_justification(self):
        doc = _golden_mode_contract()
        doc["reuse_source"] = "extension"
        if "reuse_justification" in doc:
            del doc["reuse_justification"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("mode-contract", doc)
        self.assertIn("reuse_justification", str(ctx.exception))

    def test_skill_extension_without_justification(self):
        doc = _golden_skill_contract()
        doc["reuse_source"] = "extension"
        if "reuse_justification" in doc:
            del doc["reuse_justification"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("skill-contract", doc)
        self.assertIn("reuse_justification", str(ctx.exception))

    def test_extension_with_justification_passes(self):
        doc = _golden_mode_contract()
        doc["reuse_source"] = "extension"
        doc["reuse_justification"] = "Base library has no Python linting support"
        gc.validate("mode-contract", doc)

    # -- 11. Override outside allowed slots ---------------------------------

    def test_override_forbidden_slot_in_library(self):
        doc = _golden_library()
        doc["override_rules"]["forbidden_slots"].append("state_machine")
        gc.validate("library", doc)

    # -- 12. Transfer without destination acceptance -------------------------

    def test_transfer_requires_acceptance_false(self):
        doc = _golden_library()
        doc["transfer_rules"]["requires_acceptance"] = False
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("requires_acceptance", str(ctx.exception))

    # -- 13. Skill duplicada sin diferencia material -------------------------
    #        (detected as duplicate artifact path in manifest)

    def test_duplicate_skill_no_material_difference(self):
        doc = _golden_generation_manifest()
        art1 = {
            "path": "skills/TestProject-auditor/SKILL.md",
            "type": "skill-entrypoint",
            "sha256": _FAKE_SHA,
        }
        doc["artifacts"] = [art1, copy.deepcopy(art1)]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("generation-manifest", doc)
        self.assertIn("duplicate", str(ctx.exception))

    # -- Unknown fields (additionalProperties: false) -----------------------

    def test_unknown_field_in_run(self):
        doc = _golden_run()
        doc["secret_key"] = "should-not-be-here"
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("run", doc)
        self.assertIn("unknown", str(ctx.exception).lower())

    def test_unknown_field_in_manifest(self):
        doc = _golden_generation_manifest()
        doc["extra_field"] = True
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_unknown_field_in_project_manifest(self):
        doc = _golden_project_manifest()
        doc["secrets"] = {"api_key": "xxx"}
        with self.assertRaises(gc.ContractError):
            gc.validate("project-manifest", doc)

    def test_unknown_field_in_capabilities(self):
        doc = _golden_capabilities()
        doc["admin_override"] = True
        with self.assertRaises(gc.ContractError):
            gc.validate("capabilities", doc)

    def test_unknown_field_in_handoff(self):
        doc = _golden_handoff()
        doc["secret"] = "bad"
        with self.assertRaises(gc.ContractError):
            gc.validate("handoff", doc)

    def test_unknown_field_in_scenario(self):
        doc = _golden_scenario()
        doc["answer"] = 42
        with self.assertRaises(gc.ContractError):
            gc.validate("scenario", doc)

    # -- Wrong schema_version -----------------------------------------------

    def test_wrong_schema_version_run(self):
        doc = _golden_run()
        doc["schema_version"] = 999
        with self.assertRaises(gc.ContractError):
            gc.validate("run", doc)

    def test_wrong_schema_version_manifest(self):
        doc = _golden_generation_manifest()
        doc["schema_version"] = 0
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- Creator tries to set Host-only status ------------------------------

    def test_creator_cannot_set_accepted(self):
        doc = _golden_generation_manifest()
        doc["status"] = "ACCEPTED"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_creator_cannot_set_active(self):
        doc = _golden_generation_manifest()
        doc["status"] = "ACTIVE"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- Invalid SHA-256 hashes ---------------------------------------------

    def test_invalid_sha256_in_manifest(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["sha256"] = "not-a-hash"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_invalid_sha256_in_project_hashes(self):
        doc = _golden_project_manifest()
        doc["hashes"] = {"file.py": "short"}
        with self.assertRaises(gc.ContractError):
            gc.validate("project-manifest", doc)

    def test_invalid_root_identity(self):
        doc = _golden_project_manifest()
        doc["root_identity"] = "not-sha256"
        with self.assertRaises(gc.ContractError):
            gc.validate("project-manifest", doc)

    # -- Empty artifacts list -----------------------------------------------

    def test_empty_artifacts(self):
        doc = _golden_generation_manifest()
        doc["artifacts"] = []
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- Invalid artifact type ----------------------------------------------

    def test_invalid_artifact_type(self):
        doc = _golden_generation_manifest()
        doc["artifacts"][0]["type"] = "executable"
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- Handoff self-invocation --------------------------------------------

    def test_handoff_self_invocation(self):
        doc = _golden_handoff()
        doc["target_actor"] = doc["source_actor"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("handoff", doc)
        self.assertIn("differ", str(ctx.exception))

    # -- Invalid handoff type -----------------------------------------------

    def test_invalid_handoff_type(self):
        doc = _golden_handoff()
        doc["type"] = "creator.self.approve"
        with self.assertRaises(gc.ContractError):
            gc.validate("handoff", doc)

    # -- Invalid scenario SR link -------------------------------------------

    def test_invalid_sr_link(self):
        doc = _golden_scenario()
        doc["sr_links"] = ["NOT-SR-1"]
        with self.assertRaises(gc.ContractError):
            gc.validate("scenario", doc)

    # -- Invalid scenario type ----------------------------------------------

    def test_invalid_scenario_type(self):
        doc = _golden_scenario()
        doc["type"] = "magic"
        with self.assertRaises(gc.ContractError):
            gc.validate("scenario", doc)

    # -- Invalid instruction scope ------------------------------------------

    def test_invalid_instruction_scope(self):
        doc = _golden_instructions_index()
        doc["entries"][0]["scope"] = "universe"
        with self.assertRaises(gc.ContractError):
            gc.validate("instructions-index", doc)

    # -- Invalid drift status -----------------------------------------------

    def test_invalid_drift_status(self):
        doc = _golden_drift()
        doc["entries"][0]["status"] = "DRIFTED"
        with self.assertRaises(gc.ContractError):
            gc.validate("drift", doc)

    # -- Invalid backup disposition -----------------------------------------

    def test_invalid_backup_disposition(self):
        doc = _golden_backup()
        doc["entries"][0]["disposition"] = "force-overwrite"
        with self.assertRaises(gc.ContractError):
            gc.validate("backup", doc)

    # -- Invalid promotion verdict ------------------------------------------

    def test_invalid_promotion_verdict(self):
        doc = _golden_promotion()
        doc["acceptance_record"]["verdict"] = "APPROVED"
        with self.assertRaises(gc.ContractError):
            gc.validate("promotion", doc)

    # -- Library: extension rules cannot be relaxed -------------------------

    def test_extension_justification_required(self):
        doc = _golden_library()
        doc["extension_rules"]["requires_justification"] = False
        with self.assertRaises(gc.ContractError):
            gc.validate("library", doc)

    def test_extension_must_demonstrate(self):
        doc = _golden_library()
        doc["extension_rules"]["must_demonstrate_no_prior_layer"] = False
        with self.assertRaises(gc.ContractError):
            gc.validate("library", doc)

    # -- Mode contract: empty triggers/invariants ---------------------------

    def test_mode_empty_triggers(self):
        doc = _golden_mode_contract()
        doc["triggers"] = []
        with self.assertRaises(gc.ContractError):
            gc.validate("mode-contract", doc)

    def test_mode_empty_invariants(self):
        doc = _golden_mode_contract()
        doc["invariants"] = []
        with self.assertRaises(gc.ContractError):
            gc.validate("mode-contract", doc)

    # -- Skill contract: empty files ----------------------------------------

    def test_skill_empty_files(self):
        doc = _golden_skill_contract()
        doc["files"] = []
        with self.assertRaises(gc.ContractError):
            gc.validate("skill-contract", doc)

    # -- Unknown schema name ------------------------------------------------

    def test_unknown_schema(self):
        with self.assertRaises(gc.ContractError):
            gc.validate("nonexistent-schema", {})

    # -- Non-dict input -----------------------------------------------------

    def test_non_dict_input(self):
        with self.assertRaises(gc.ContractError):
            gc.validate("run", [])

    def test_none_input(self):
        with self.assertRaises(gc.ContractError):
            gc.validate("run", None)

    def test_string_input(self):
        with self.assertRaises(gc.ContractError):
            gc.validate("run", "not a dict")

    # -- Context policy invalid values -------------------------------------

    def test_zero_entrypoint_max_bytes(self):
        doc = _golden_generation_manifest()
        doc["context_policy"]["skill_entrypoint_max_bytes"] = 0
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_warning_ratio_out_of_range(self):
        doc = _golden_generation_manifest()
        doc["context_policy"]["warning_ratio"] = 1.5
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    def test_warning_ratio_zero(self):
        doc = _golden_generation_manifest()
        doc["context_policy"]["warning_ratio"] = 0
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", doc)

    # -- Backup: verified not bool -----------------------------------------

    def test_backup_verified_not_bool(self):
        doc = _golden_backup()
        doc["verified"] = "yes"
        with self.assertRaises(gc.ContractError):
            gc.validate("backup", doc)

    # -- Rollback: verification missing fields -----------------------------

    def test_rollback_missing_hashes_match(self):
        doc = _golden_rollback()
        del doc["verification"]["hashes_match"]
        with self.assertRaises(gc.ContractError):
            gc.validate("rollback", doc)


# ===========================================================================
# Immutability test: negative cases must not write anything
# ===========================================================================


class TestFailClosedNoWrite(unittest.TestCase):
    """Verifica que rechazos no dejan escritura parcial."""

    def test_symlink_rejection_preserves_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            f = gen / "good.md"
            f.write_text("ok")
            link = gen / "bad.md"
            link.symlink_to(f)
            state_before = sorted(p.name for p in gen.iterdir())

            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "good.md", "type": "manifest",
                 "sha256": gc.compute_file_sha256(f)},
                {"path": "bad.md", "type": "manifest",
                 "sha256": gc.compute_file_sha256(f)},
            ]
            with self.assertRaises(gc.ContractError):
                gc.verify_manifest_hashes(manifest, str(gen))

            state_after = sorted(p.name for p in gen.iterdir())
            self.assertEqual(state_before, state_after)

    def test_hash_mismatch_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen = Path(tmp) / "generated"
            gen.mkdir()
            f = gen / "file.md"
            f.write_text("content")
            content_before = f.read_bytes()

            manifest = _golden_generation_manifest()
            manifest["artifacts"] = [
                {"path": "file.md", "type": "manifest",
                 "sha256": "0" * 64},
            ]
            gc.verify_manifest_hashes(manifest, str(gen))
            self.assertEqual(f.read_bytes(), content_before)


# ===========================================================================
# Validate JSON file from disk
# ===========================================================================


class TestValidateJsonFile(unittest.TestCase):
    """Validate loading and validating JSON files from disk."""

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(_golden_run(), f)
            f.flush()
            try:
                doc = gc.validate_json_file("run", f.name)
                self.assertEqual(doc["generation_id"], "gen-001")
            finally:
                os.unlink(f.name)

    def test_missing_file(self):
        with self.assertRaises(gc.ContractError):
            gc.validate_json_file("run", "/nonexistent/file.json")

    def test_symlink_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text(json.dumps(_golden_run()))
            link = Path(tmp) / "link.json"
            link.symlink_to(real)
            with self.assertRaises(gc.ContractError) as ctx:
                gc.validate_json_file("run", str(link))
            self.assertIn("symlink", str(ctx.exception))


# ===========================================================================
# Fixtures contain no real paths, credentials, or projects
# ===========================================================================


class TestFixtureSanitization(unittest.TestCase):
    """Gate: fixtures no contienen rutas reales, credenciales ni proyectos reales."""

    def _check_no_real_content(self, doc):
        text = json.dumps(doc)
        for forbidden in [
            "/home/", "/Users/", "C:\\", "api_key", "password",
            "token", "secret", "Syncify", "RehabWeb",
        ]:
            self.assertNotIn(
                forbidden, text,
                f"Fixture contains forbidden content: {forbidden}",
            )

    def test_golden_run_sanitized(self):
        self._check_no_real_content(_golden_run())

    def test_golden_manifest_sanitized(self):
        self._check_no_real_content(_golden_generation_manifest())

    def test_golden_project_sanitized(self):
        self._check_no_real_content(_golden_project_manifest())

    def test_golden_capabilities_sanitized(self):
        self._check_no_real_content(_golden_capabilities())

    def test_golden_scenario_sanitized(self):
        self._check_no_real_content(_golden_scenario())

    def test_golden_handoff_sanitized(self):
        self._check_no_real_content(_golden_handoff())

    def test_golden_drift_sanitized(self):
        self._check_no_real_content(_golden_drift())

    def test_golden_backup_sanitized(self):
        self._check_no_real_content(_golden_backup())

    def test_golden_promotion_sanitized(self):
        self._check_no_real_content(_golden_promotion())

    def test_golden_rollback_sanitized(self):
        self._check_no_real_content(_golden_rollback())

    def test_golden_library_sanitized(self):
        self._check_no_real_content(_golden_library())

    def test_golden_mode_contract_sanitized(self):
        self._check_no_real_content(_golden_mode_contract())

    def test_golden_skill_contract_sanitized(self):
        self._check_no_real_content(_golden_skill_contract())

    def test_golden_discovery_sanitized(self):
        self._check_no_real_content(_golden_discovery())

    def test_golden_design_sanitized(self):
        self._check_no_real_content(_golden_design())

    def test_golden_tests_spec_sanitized(self):
        self._check_no_real_content(_golden_tests_spec())


class TestReferenceFixtures(unittest.TestCase):
    """Valida que los fixtures de referencia (§4.6) son válidos y están saneados."""

    def test_syncify_fixture_valid(self):
        pm = ROOT / "fixtures" / "syncify" / "project-manifest.json"
        gm = ROOT / "fixtures" / "syncify" / "golden-manifest.json"
        doc_pm = gc.validate_json_file("project-manifest", str(pm))
        doc_gm = gc.validate_json_file("generation-manifest", str(gm))
        self.assertEqual(doc_pm["name"], "Syncify")
        self.assertEqual(doc_gm["status"], "GENERATED")

    def test_rehabweb_fixture_valid(self):
        pm = ROOT / "fixtures" / "rehabweb" / "project-manifest.json"
        gm = ROOT / "fixtures" / "rehabweb" / "golden-manifest.json"
        doc_pm = gc.validate_json_file("project-manifest", str(pm))
        doc_gm = gc.validate_json_file("generation-manifest", str(gm))
        self.assertEqual(doc_pm["name"], "RehabWeb")
        self.assertEqual(doc_gm["status"], "GENERATED")


# ===========================================================================
# Source registry: registro canónico de fuentes externas de skills
# ===========================================================================


def _golden_source_registry():
    return {
        "schema_version": 1,
        "policy": {
            "acquisition": "manual-pin-only",
            "auto_install_forbidden": True,
            "npx_marketplace_forbidden": True,
            "staging_outside_canonical_tree": True,
            "host_validate_before_activation": True,
        },
        "analysis_inventory": {
            "entries": 2,
            "generated_at": "2026-09-17",
            "sha256": _FAKE_SHA,
            "location": "External audit workspace outside the canonical tree",
        },
        "sources": [
            {
                "source_id": "example-skills",
                "title": "Example Skills",
                "publisher": "Example Org",
                "kind": "skill-repository",
                "canonical_url": "https://github.com/example/skills",
                "revision": "a" * 40,
                "retrieved_at": "2026-09-17",
                "provenance_status": "pinned",
                "license": "MIT",
                "license_status": "open",
                "status": "CANDIDATE",
                "decision_summary": "Process patterns to convert under framework contracts.",
            },
            {
                "source_id": "example-standard",
                "title": "Example Standard",
                "publisher": "Example Body",
                "kind": "standard",
                "provenance_status": "unpinned",
                "license": "Copyrighted standard text",
                "license_status": "proprietary",
                "status": "REFERENCE",
                "decision_summary": "Design inspiration only; no conversion without pinning.",
            },
        ],
    }


class TestSourceRegistry(unittest.TestCase):
    """El registro de fuentes es fail-closed: sin pin ni licencia no hay candidata."""

    def test_golden(self):
        gc.validate("source-registry", _golden_source_registry())

    def test_canonical_registry_file_valid(self):
        registry = ROOT / "library" / "source-registry.json"
        self.assertTrue(registry.is_file())
        doc = gc.validate_json_file("source-registry", str(registry))
        self.assertGreaterEqual(len(doc["sources"]), 20)
        ids = [s["source_id"] for s in doc["sources"]]
        self.assertEqual(len(ids), len(set(ids)))
        candidates = [s for s in doc["sources"] if s["status"] == "CANDIDATE"]
        for source in candidates:
            self.assertEqual(source["provenance_status"], "pinned")
            self.assertIn(source["license_status"], ("open", "mixed"))

    # -- proceduralización: sin ubicación/commit no es registrable ----------

    def test_repository_without_url_rejected(self):
        doc = _golden_source_registry()
        del doc["sources"][0]["canonical_url"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("canonical_url", str(ctx.exception))

    def test_repository_without_revision_rejected(self):
        doc = _golden_source_registry()
        del doc["sources"][0]["revision"]
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    def test_repository_unpinned_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][0]["provenance_status"] = "unpinned"
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("pinned", str(ctx.exception))

    def test_repository_without_retrieval_date_rejected(self):
        doc = _golden_source_registry()
        del doc["sources"][0]["retrieved_at"]
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    # -- candidata exige procedencia fijada y licencia resoluble ------------

    def test_candidate_with_unresolved_license_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][0]["license_status"] = "unresolved"
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("license_status", str(ctx.exception))

    def test_candidate_unpinned_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][0]["provenance_status"] = "unpinned"
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    # -- política de adquisición inmutable ----------------------------------

    def test_auto_install_true_rejected(self):
        doc = _golden_source_registry()
        doc["policy"]["auto_install_forbidden"] = False
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("auto_install_forbidden", str(ctx.exception))

    def test_staging_constant_relaxed_rejected(self):
        doc = _golden_source_registry()
        doc["policy"]["staging_outside_canonical_tree"] = False
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    # -- integridad del documento -------------------------------------------

    def test_duplicate_source_id_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][1] = dict(doc["sources"][1])
        doc["sources"][1]["source_id"] = doc["sources"][0]["source_id"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("duplicates", str(ctx.exception))

    def test_unknown_field_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][0]["installer"] = "npx"
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    def test_bad_inventory_sha_rejected(self):
        doc = _golden_source_registry()
        doc["analysis_inventory"]["sha256"] = "not-a-hash"
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)

    def test_local_path_in_inventory_location_rejected(self):
        doc = _golden_source_registry()
        doc["analysis_inventory"]["location"] = "/home/alan/external/inventory"
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("source-registry", doc)
        self.assertIn("local filesystem", str(ctx.exception))

    def test_unknown_status_rejected(self):
        doc = _golden_source_registry()
        doc["sources"][0]["status"] = "ACTIVE-ISH"
        with self.assertRaises(gc.ContractError):
            gc.validate("source-registry", doc)


# ===========================================================================
# Library hardening: sin activación/escenarios/procedencia no es seleccionable
# ===========================================================================


class TestLibraryHardening(unittest.TestCase):
    """La biblioteca no selecciona entradas sin procedencia, activación ni escenarios."""

    def test_catalog_pattern_requires_activation_criteria(self):
        doc = _golden_library()
        del doc["catalog_patterns"][0]["activation_criteria"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("activation_criteria", str(ctx.exception))

    def test_catalog_pattern_empty_activation_criteria_rejected(self):
        doc = _golden_library()
        doc["catalog_patterns"][0]["activation_criteria"] = []
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("activation_criteria", str(ctx.exception))

    def test_catalog_pattern_requires_scenarios(self):
        doc = _golden_library()
        del doc["catalog_patterns"][0]["scenarios"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("scenarios", str(ctx.exception))

    def test_catalog_pattern_empty_invariants_rejected(self):
        doc = _golden_library()
        doc["catalog_patterns"][0]["invariants"] = []
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("invariants", str(ctx.exception))

    def test_base_skill_requires_scenarios(self):
        doc = _golden_library()
        del doc["base_skills"][0]["scenarios"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("scenarios", str(ctx.exception))

    def test_base_skill_provenance_requires_source(self):
        doc = _golden_library()
        del doc["base_skills"][0]["provenance"]["source"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("source", str(ctx.exception))

    def test_catalog_pattern_provenance_requires_source(self):
        doc = _golden_library()
        del doc["catalog_patterns"][0]["provenance"]["source"]
        with self.assertRaises(gc.ContractError) as ctx:
            gc.validate("library", doc)
        self.assertIn("source", str(ctx.exception))

    def test_external_source_reference_accepted(self):
        doc = _golden_library()
        doc["catalog_patterns"][0]["provenance"]["source"] = "example-skills"
        doc["catalog_patterns"][0]["provenance"]["commit"] = "a" * 40
        gc.validate("library", doc)


if __name__ == "__main__":
    unittest.main()
