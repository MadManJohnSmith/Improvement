"""Generational contract validator — stdlib only, no partial mutation.

Validates JSON documents against the C0 generation schemas using pure Python.
No external dependencies. All validation is fail-closed: any error rejects the
entire document without writing anything.

    python3 -B -m scripts.generation_contracts --help

Versión del schema: 1
"""

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Schema registry: maps schema name → required fields, field types, enums
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SR_RE = re.compile(r"^SR-[0-9]+$")
_PATH_SAFE_RE = re.compile(r"^(?!.*\.\.)(?!/)(?!.*//).")


def _is_sha256(v):
    return isinstance(v, str) and bool(_SHA256_RE.match(v))


def _is_nonempty_str(v):
    return isinstance(v, str) and len(v) > 0


def _is_nonblank_str(v):
    return isinstance(v, str) and bool(v.strip())


def _is_iso_datetime(v):
    """Loose check for ISO 8601 date-time string."""
    if not isinstance(v, str):
        return False
    return bool(re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", v
    ))


# ---------------------------------------------------------------------------
# Run statuses
# ---------------------------------------------------------------------------

RUN_STATUSES = frozenset([
    "CREATED", "DISCOVERING", "DESIGNING", "GENERATING", "GENERATED",
    "VALIDATING", "BACKED_UP", "STAGED", "ACCEPTING", "ACTIVE",
    "RETAINED", "REPAIRING", "ROLLED_BACK", "RECOVERY_REQUIRED",
    "CANCELLED",
])

CREATOR_MAX_STATUS = frozenset([
    "CREATED", "DISCOVERING", "DESIGNING", "GENERATING", "GENERATED",
])

HOST_ONLY_STATUSES = RUN_STATUSES - CREATOR_MAX_STATUS

# ---------------------------------------------------------------------------
# Generation manifest statuses
# ---------------------------------------------------------------------------

GENERATION_MANIFEST_STATUSES = frozenset(["GENERATED"])

# ---------------------------------------------------------------------------
# Artifact types
# ---------------------------------------------------------------------------

ARTIFACT_TYPES = frozenset([
    "skill-entrypoint", "mode-definition", "mode-internal", "mode-reference",
    "mode-template", "mode-adapter", "skill-internal", "skill-reference",
    "skill-template", "skill-adapter", "contract", "reference", "template",
    "adapter", "manifest", "plan", "report", "asset",
])

# ---------------------------------------------------------------------------
# Reuse sources (skill selection strategy)
# ---------------------------------------------------------------------------

REUSE_SOURCES = frozenset([
    "base-library", "specialized-catalog", "composition", "override",
    "extension",
])

# ---------------------------------------------------------------------------
# Scenario types
# ---------------------------------------------------------------------------

SCENARIO_TYPES = frozenset([
    "positive", "negative", "boundary", "tool-denial", "capability-denial",
    "missing-capability", "prompt-injection", "cycle", "invalid-handoff",
    "base-obsolete", "candidate-obsolete", "idempotence", "scope-violation",
    "write-violation",
])

SCENARIO_VERDICTS = frozenset(["PASS", "FAIL", "BLOCKED", "NOT_COVERED"])

VERIFICATION_STATES = frozenset([
    "PASS", "FAIL", "BLOCKED", "NOT_COVERED", "UNVERIFIED",
    "IMPLEMENTED_NOT_APPLIED",
])

HOLDOUT_FAMILIES = frozenset([
    "prompt-injection-in-repository", "ipc-argument-drift",
    "persistent-data-without-backup", "third-attempt-denial",
    "stale-candidate-evidence",
])

CONTRACT_KINDS = frozenset(["mode", "skill"])

# ---------------------------------------------------------------------------
# Handoff event types
# ---------------------------------------------------------------------------

HANDOFF_TYPES = frozenset([
    "creator.generation.complete", "bootstrap.accept.request",
    "host.accepted", "host.retained", "repair.complete",
    "repair.blocked", "host.rejected",
])

# ---------------------------------------------------------------------------
# Drift statuses
# ---------------------------------------------------------------------------

DRIFT_STATUSES = frozenset([
    "CURRENT", "SOURCE_DRIFT", "NON_GOVERNING_CHANGE", "LOCAL_SKILL_EDIT",
    "CONTRACT_DRIFT", "ORPHANED", "AMBIGUOUS_SCOPE", "STALE_REFERENCE",
    "UNVERIFIED",
])

DRIFT_ACTIONS = frozenset(["none", "regenerate", "update", "conflict", "remove"])

# ---------------------------------------------------------------------------
# Backup dispositions
# ---------------------------------------------------------------------------

BACKUP_DISPOSITIONS = frozenset([
    "identical", "new", "managed-modified", "external", "local-edit",
])

# ---------------------------------------------------------------------------
# Promotion statuses
# ---------------------------------------------------------------------------

PROMOTION_STATUSES = frozenset(["PLANNED", "SMOKE_PASSED", "PROMOTED", "ROLLED_BACK"])
PROMOTION_VERDICTS = frozenset(["ACCEPTED", "RETAINED", "REJECTED"])

# ---------------------------------------------------------------------------
# Instruction scopes
# ---------------------------------------------------------------------------

INSTRUCTION_SCOPES = frozenset(["global", "workspace", "directory", "file"])

# ---------------------------------------------------------------------------
# Core validation helpers
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """Raised when a document violates its generation contract."""


def _require(condition, msg):
    if not condition:
        raise ContractError(msg)


def _require_type(value, expected_type, field_name):
    _require(
        isinstance(value, expected_type),
        f"{field_name}: expected {expected_type.__name__}, got {type(value).__name__}",
    )


def _require_enum(value, allowed, field_name):
    try:
        accepted = value in allowed
    except TypeError:
        accepted = False
    _require(
        accepted,
        f"{field_name}: {value!r} not in {sorted(allowed)}",
    )


def _require_fields(doc, required, schema_name):
    for f in required:
        _require(f in doc, f"{schema_name}: missing required field '{f}'")


def _reject_unknown(doc, known, schema_name):
    unknown = set(doc.keys()) - set(known)
    _require(
        not unknown,
        f"{schema_name}: unknown fields {sorted(unknown)}",
    )


def _is_nonempty_str_list(values):
    return (isinstance(values, list)
            and all(_is_nonempty_str(v) for v in values))


_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _is_date(v):
    return isinstance(v, str) and bool(_DATE_RE.match(v))


# ---------------------------------------------------------------------------
# Per-schema validators
# ---------------------------------------------------------------------------


def validate_run(doc):
    """Validate a run.json document."""
    schema = "run"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "status", "created_at",
        "project", "framework_revision",
    ]
    known = required + [
        "updated_at", "templates_revision", "budget", "directories",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version {doc['schema_version']}")
    _require(_is_nonempty_str(doc["generation_id"]),
             f"{schema}: generation_id must be non-empty string")
    _require_enum(doc["status"], RUN_STATUSES, f"{schema}.status")
    _require(_is_iso_datetime(doc["created_at"]),
             f"{schema}: created_at must be ISO 8601 datetime")

    proj = doc["project"]
    _require_type(proj, dict, f"{schema}.project")
    _require_fields(proj, ["name"], f"{schema}.project")
    _reject_unknown(proj, ["name", "root_identity"], f"{schema}.project")
    _require(_is_nonempty_str(proj["name"]),
             f"{schema}.project.name must be non-empty")

    _require(_is_nonempty_str(doc["framework_revision"]),
             f"{schema}: framework_revision must be non-empty string")

    if "budget" in doc and doc["budget"] is not None:
        b = doc["budget"]
        _require_type(b, dict, f"{schema}.budget")
        _reject_unknown(b,
                        ["max_attempts", "max_tokens", "max_seconds", "max_cost_usd"],
                        f"{schema}.budget")

    if "directories" in doc and doc["directories"] is not None:
        d = doc["directories"]
        _require_type(d, dict, f"{schema}.directories")
        valid_dirs = {
            "inputs", "discovery", "design", "tests", "generated",
            "validation", "acceptance", "retained", "backup", "promotion",
        }
        _reject_unknown(d, valid_dirs, f"{schema}.directories")


def validate_generation_manifest(doc):
    """Validate a generation-manifest.json document."""
    schema = "generation-manifest"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "status", "project", "creator",
        "framework", "artifacts", "required_capabilities",
        "forbidden_capabilities", "effective_routing_digest",
        "context_policy", "license_provenance",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, required, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["generation_id"]),
             f"{schema}: generation_id must be non-empty")
    _require_enum(doc["status"], GENERATION_MANIFEST_STATUSES,
                  f"{schema}.status")

    # project
    proj = doc["project"]
    _require_type(proj, dict, f"{schema}.project")
    _require_fields(proj, ["name", "root_identity", "base_revision"],
                    f"{schema}.project")
    _reject_unknown(proj, ["name", "root_identity", "base_revision"],
                    f"{schema}.project")
    _require(_is_nonempty_str(proj["name"]), f"{schema}.project.name")
    _require(_is_sha256(proj["root_identity"]),
             f"{schema}.project.root_identity must be sha256")

    # creator
    cr = doc["creator"]
    _require_type(cr, dict, f"{schema}.creator")
    _require_fields(cr, ["session_ref", "runtime_version"],
                    f"{schema}.creator")
    _reject_unknown(cr, ["session_ref", "runtime_version"],
                    f"{schema}.creator")

    # framework
    fw = doc["framework"]
    _require_type(fw, dict, f"{schema}.framework")
    _require_fields(fw, ["revision"], f"{schema}.framework")
    _reject_unknown(fw, ["revision", "templates_revision"],
                    f"{schema}.framework")

    # artifacts
    arts = doc["artifacts"]
    _require_type(arts, list, f"{schema}.artifacts")
    _require(len(arts) > 0, f"{schema}: artifacts must not be empty")
    seen_paths = set()
    for i, a in enumerate(arts):
        _validate_artifact_entry(a, f"{schema}.artifacts[{i}]")
        _require(a["path"] not in seen_paths,
                 f"{schema}.artifacts[{i}]: duplicate path {a['path']!r}")
        seen_paths.add(a["path"])

    # capabilities
    for cap_field in ("required_capabilities", "forbidden_capabilities"):
        _require_type(doc[cap_field], list, f"{schema}.{cap_field}")

    # routing digest
    _require(_is_nonempty_str(doc["effective_routing_digest"]),
             f"{schema}: effective_routing_digest must be non-empty")

    # context policy
    _validate_context_policy(doc["context_policy"], f"{schema}.context_policy")

    # license provenance
    _require_type(doc["license_provenance"], list,
                  f"{schema}.license_provenance")
    for i, lp in enumerate(doc["license_provenance"]):
        _validate_provenance_entry(lp, f"{schema}.license_provenance[{i}]")


def _validate_artifact_entry(a, prefix):
    _require_type(a, dict, prefix)
    _require_fields(a, ["path", "type", "sha256"], prefix)
    _reject_unknown(a, ["path", "type", "sha256", "size_bytes"], prefix)
    _require(_is_nonempty_str(a["path"]), f"{prefix}.path")
    _require(bool(_PATH_SAFE_RE.match(a["path"])),
             f"{prefix}.path: unsafe path {a['path']!r}")
    _require_enum(a["type"], ARTIFACT_TYPES, f"{prefix}.type")
    _require(_is_sha256(a["sha256"]), f"{prefix}.sha256")
    if "size_bytes" in a:
        _require(isinstance(a["size_bytes"], int) and a["size_bytes"] >= 0,
                 f"{prefix}.size_bytes must be non-negative integer")


def _validate_context_policy(cp, prefix):
    _require_type(cp, dict, prefix)
    _require_fields(cp, [
        "skill_entrypoint_max_bytes", "support_file_max_bytes",
        "warning_ratio",
    ], prefix)
    _reject_unknown(cp, [
        "skill_entrypoint_max_bytes", "support_file_max_bytes",
        "warning_ratio", "hot_paths",
    ], prefix)
    _require(isinstance(cp["skill_entrypoint_max_bytes"], int)
             and cp["skill_entrypoint_max_bytes"] > 0,
             f"{prefix}.skill_entrypoint_max_bytes must be positive int")
    _require(isinstance(cp["support_file_max_bytes"], int)
             and cp["support_file_max_bytes"] > 0,
             f"{prefix}.support_file_max_bytes must be positive int")
    _require(isinstance(cp["warning_ratio"], (int, float))
             and 0 < cp["warning_ratio"] <= 1,
             f"{prefix}.warning_ratio must be in (0, 1]")
    if "hot_paths" in cp and cp["hot_paths"] is not None:
        _require_type(cp["hot_paths"], dict, f"{prefix}.hot_paths")
        for k, v in cp["hot_paths"].items():
            _require(isinstance(v, int) and v > 0,
                     f"{prefix}.hot_paths.{k} must be positive int")


def _validate_provenance_entry(lp, prefix):
    _require_type(lp, dict, prefix)
    _require_fields(lp, ["file", "source", "license"], prefix)
    _reject_unknown(lp, ["file", "source", "license", "commit"], prefix)


def validate_project_manifest(doc):
    """Validate a project-manifest.json document."""
    schema = "project-manifest"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "name", "root_identity", "base_revision",
        "inventory", "authority",
    ]
    known = required + ["hashes", "capabilities_ref"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["name"]), f"{schema}.name")
    _require(_is_sha256(doc["root_identity"]),
             f"{schema}.root_identity must be sha256")
    _require(_is_nonempty_str(doc["base_revision"]),
             f"{schema}.base_revision")

    inv = doc["inventory"]
    _require_type(inv, dict, f"{schema}.inventory")
    _require_fields(inv, ["total_files", "total_bytes", "languages", "areas"],
                    f"{schema}.inventory")
    _reject_unknown(inv, ["total_files", "total_bytes", "languages", "areas"],
                    f"{schema}.inventory")

    auth = doc["authority"]
    _require_type(auth, dict, f"{schema}.authority")
    _require_fields(auth, ["holder", "source"], f"{schema}.authority")
    _reject_unknown(auth, ["holder", "source"], f"{schema}.authority")

    if "hashes" in doc and doc["hashes"] is not None:
        _require_type(doc["hashes"], dict, f"{schema}.hashes")
        for k, v in doc["hashes"].items():
            _require(_is_sha256(v), f"{schema}.hashes.{k} must be sha256")


def validate_instructions_index(doc):
    """Validate an instructions-index.json document."""
    schema = "instructions-index"
    _require_type(doc, dict, schema)
    _require_fields(doc, ["schema_version", "entries"], schema)
    _reject_unknown(doc, ["schema_version", "entries"], schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require_type(doc["entries"], list, f"{schema}.entries")
    for i, e in enumerate(doc["entries"]):
        _validate_instruction_entry(e, f"{schema}.entries[{i}]")


def _validate_instruction_entry(e, prefix):
    _require_type(e, dict, prefix)
    _require_fields(e, ["path", "scope", "precedence", "sha256"], prefix)
    _reject_unknown(e, [
        "path", "scope", "precedence", "sha256",
        "sections", "facts", "constraints", "unknowns", "conflicts",
    ], prefix)
    _require(_is_nonempty_str(e["path"]), f"{prefix}.path")
    _require_enum(e["scope"], INSTRUCTION_SCOPES, f"{prefix}.scope")
    _require(isinstance(e["precedence"], int) and e["precedence"] >= 0,
             f"{prefix}.precedence must be non-negative int")
    _require(_is_sha256(e["sha256"]), f"{prefix}.sha256")


def validate_capabilities(doc):
    """Validate a capabilities.json document."""
    schema = "capabilities"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "capability_id", "session_id", "project",
        "executor", "roots", "scope",
    ]
    known = required + ["required_capabilities", "forbidden_capabilities"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["capability_id"]), f"{schema}.capability_id")

    roots = doc["roots"]
    _require_type(roots, dict, f"{schema}.roots")
    _require_fields(roots, [
        "product_read", "framework_execute", "workspace_write",
    ], f"{schema}.roots")
    _reject_unknown(roots, [
        "product_read", "framework_execute", "workspace_write",
    ], f"{schema}.roots")
    for k in ("product_read", "framework_execute", "workspace_write"):
        _require_type(roots[k], list, f"{schema}.roots.{k}")

    _require_type(doc["scope"], list, f"{schema}.scope")


def validate_scenario(doc):
    """Validate a scenario entry from scenarios.jsonl."""
    schema = "scenario"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "scenario_id", "type", "description",
        "input", "expected", "sr_links",
    ]
    known = required + [
        "target_mode", "target_skill", "holdout_family",
        "verification_state",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["scenario_id"]), f"{schema}.scenario_id")
    _require_enum(doc["type"], SCENARIO_TYPES, f"{schema}.type")
    _require(_is_nonempty_str(doc["description"]), f"{schema}.description")
    _require_type(doc["input"], dict, f"{schema}.input")

    exp = doc["expected"]
    _require_type(exp, dict, f"{schema}.expected")
    _require_fields(exp, ["verdict"], f"{schema}.expected")
    _reject_unknown(exp, ["verdict", "evidence_type", "description"],
                    f"{schema}.expected")
    _require_enum(exp["verdict"], SCENARIO_VERDICTS, f"{schema}.expected.verdict")

    _require_type(doc["sr_links"], list, f"{schema}.sr_links")
    for i, sr in enumerate(doc["sr_links"]):
        _require(isinstance(sr, str) and bool(_SR_RE.match(sr)),
                 f"{schema}.sr_links[{i}]: must match SR-N pattern")

    if "verification_state" in doc:
        _require_enum(doc["verification_state"], VERIFICATION_STATES,
                      f"{schema}.verification_state")


def validate_acceptance_plan(doc):
    """Validate generated/acceptance-plan.json using the current Host shape."""
    schema = "acceptance-plan"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "requirements",
        "public_scenarios", "holdout_families", "gates", "creator_limit",
    ]
    known = required + ["status", "candidate_base_revision"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonblank_str(doc["generation_id"]),
             f"{schema}.generation_id must be non-empty")
    if "status" in doc:
        _require(doc["status"] == "GENERATED",
                 f"{schema}.status must be GENERATED")
    if "candidate_base_revision" in doc:
        _require(_is_nonblank_str(doc["candidate_base_revision"]),
                 f"{schema}.candidate_base_revision must be non-empty")

    requirements = doc["requirements"]
    _require_type(requirements, list, f"{schema}.requirements")
    _require(bool(requirements), f"{schema}.requirements must not be empty")
    requirement_ids = set()
    for i, requirement in enumerate(requirements):
        prefix = f"{schema}.requirements[{i}]"
        _require_type(requirement, dict, prefix)
        fields = ["id", "criterion", "evidence"]
        _require_fields(requirement, fields, prefix)
        _reject_unknown(requirement, fields, prefix)
        requirement_id = requirement["id"]
        _require(isinstance(requirement_id, str)
                 and bool(_SR_RE.fullmatch(requirement_id)),
                 f"{prefix}.id must match SR-N")
        _require(requirement_id not in requirement_ids,
                 f"{schema}: duplicate requirement {requirement_id!r}")
        requirement_ids.add(requirement_id)
        for field in ("criterion", "evidence"):
            _require(_is_nonblank_str(requirement[field]),
                     f"{prefix}.{field} must be non-empty")

    scenarios = doc["public_scenarios"]
    _require_type(scenarios, list, f"{schema}.public_scenarios")
    _require(bool(scenarios), f"{schema}.public_scenarios must not be empty")
    scenario_ids = set()
    for i, scenario in enumerate(scenarios):
        prefix = f"{schema}.public_scenarios[{i}]"
        _require_type(scenario, dict, prefix)
        fields = ["id", "type", "target", "expected"]
        _require_fields(scenario, fields, prefix)
        _reject_unknown(scenario, fields, prefix)
        _require(_is_nonblank_str(scenario["id"]), f"{prefix}.id")
        _require(scenario["id"] not in scenario_ids,
                 f"{schema}: duplicate scenario id {scenario['id']!r}")
        scenario_ids.add(scenario["id"])
        _require_enum(scenario["type"], SCENARIO_TYPES, f"{prefix}.type")
        _require(_is_nonblank_str(scenario["target"]), f"{prefix}.target")
        _require_enum(scenario["expected"], SCENARIO_VERDICTS,
                      f"{prefix}.expected")

    families = doc["holdout_families"]
    _require_type(families, list, f"{schema}.holdout_families")
    _require(bool(families), f"{schema}.holdout_families must not be empty")
    seen_families = set()
    for i, family in enumerate(families):
        _require_enum(family, HOLDOUT_FAMILIES,
                      f"{schema}.holdout_families[{i}]")
        _require(family not in seen_families,
                 f"{schema}.holdout_families must not contain duplicates")
        seen_families.add(family)
    _require(isinstance(doc["gates"], list) and bool(doc["gates"])
             and all(_is_nonblank_str(gate) for gate in doc["gates"]),
             f"{schema}.gates must be a non-empty string array")
    _require(_is_nonblank_str(doc["creator_limit"]),
             f"{schema}.creator_limit must be non-empty")


def validate_handoff(doc):
    """Validate a handoff event."""
    schema = "handoff"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "type", "run_id",
        "source_actor", "target_actor", "reason",
    ]
    known = required + [
        "candidate_digest", "evidence_refs", "allowed_next_actions",
        "attempt", "parent_event_id", "idempotency_key", "timestamp",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require_enum(doc["type"], HANDOFF_TYPES, f"{schema}.type")
    _require(_is_nonempty_str(doc["run_id"]), f"{schema}.run_id")
    _require(_is_nonempty_str(doc["source_actor"]), f"{schema}.source_actor")
    _require(_is_nonempty_str(doc["target_actor"]), f"{schema}.target_actor")
    _require(doc["source_actor"] != doc["target_actor"],
             f"{schema}: source_actor and target_actor must differ")
    _require(_is_nonempty_str(doc["reason"]), f"{schema}.reason")

    if "candidate_digest" in doc and doc["candidate_digest"] is not None:
        _require(_is_sha256(doc["candidate_digest"]),
                 f"{schema}.candidate_digest must be sha256")
    if "attempt" in doc:
        _require(isinstance(doc["attempt"], int) and doc["attempt"] >= 1,
                 f"{schema}.attempt must be >= 1")


def validate_drift(doc):
    """Validate a drift analysis document."""
    schema = "drift"
    _require_type(doc, dict, schema)
    required = ["schema_version", "generation_id", "comparison_points", "entries"]
    known = required + ["update_plan_ref"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["generation_id"]), f"{schema}.generation_id")

    cp = doc["comparison_points"]
    _require_type(cp, dict, f"{schema}.comparison_points")
    _require_fields(cp, ["project_base", "accepted_generation"],
                    f"{schema}.comparison_points")
    _reject_unknown(cp, [
        "project_base", "normalized_contract", "accepted_generation",
        "installed_digest", "current_project",
    ], f"{schema}.comparison_points")

    _require_type(doc["entries"], list, f"{schema}.entries")
    for i, e in enumerate(doc["entries"]):
        prefix = f"{schema}.entries[{i}]"
        _require_type(e, dict, prefix)
        _require_fields(e, ["path", "status", "source"], prefix)
        _reject_unknown(e, ["path", "status", "source", "detail", "action"],
                        prefix)
        _require_enum(e["status"], DRIFT_STATUSES, f"{prefix}.status")
        if "action" in e:
            _require_enum(e["action"], DRIFT_ACTIONS, f"{prefix}.action")


def validate_backup(doc):
    """Validate a backup manifest."""
    schema = "backup"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "timestamp",
        "previous_generation_id", "entries", "hashes_digest", "verified",
    ]
    known = required + ["restore_plan_ref"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["generation_id"]), f"{schema}.generation_id")
    _require(_is_iso_datetime(doc["timestamp"]), f"{schema}.timestamp")
    _require(_is_sha256(doc["hashes_digest"]), f"{schema}.hashes_digest")
    _require(isinstance(doc["verified"], bool), f"{schema}.verified must be bool")

    _require_type(doc["entries"], list, f"{schema}.entries")
    for i, e in enumerate(doc["entries"]):
        prefix = f"{schema}.entries[{i}]"
        _require_type(e, dict, prefix)
        _require_fields(e, ["path", "sha256", "disposition"], prefix)
        _reject_unknown(e, ["path", "sha256", "disposition", "size_bytes",
                            "backup_path"], prefix)
        _require(_is_sha256(e["sha256"]), f"{prefix}.sha256")
        _require_enum(e["disposition"], BACKUP_DISPOSITIONS,
                      f"{prefix}.disposition")


def validate_promotion(doc):
    """Validate a promotion record."""
    schema = "promotion"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "status", "acceptance_record",
    ]
    known = required + [
        "promotion_plan", "post_promotion_smoke", "rollback_record",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require_enum(doc["status"], PROMOTION_STATUSES, f"{schema}.status")

    ar = doc["acceptance_record"]
    _require_type(ar, dict, f"{schema}.acceptance_record")
    _require_fields(ar, ["verdict", "timestamp"], f"{schema}.acceptance_record")
    _reject_unknown(ar, ["verdict", "timestamp", "evidence_refs"],
                    f"{schema}.acceptance_record")
    _require_enum(ar["verdict"], PROMOTION_VERDICTS,
                  f"{schema}.acceptance_record.verdict")


def validate_rollback(doc):
    """Validate a rollback receipt."""
    schema = "rollback"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "generation_id", "rolled_back_to", "reason",
        "timestamp", "verification",
    ]
    known = required + ["recovery_required"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["generation_id"]), f"{schema}.generation_id")
    _require(_is_nonempty_str(doc["reason"]), f"{schema}.reason")

    v = doc["verification"]
    _require_type(v, dict, f"{schema}.verification")
    _require_fields(v, ["hashes_match", "files_restored"],
                    f"{schema}.verification")
    _reject_unknown(v, ["hashes_match", "files_restored", "files_removed"],
                    f"{schema}.verification")
    _require(isinstance(v["hashes_match"], bool),
             f"{schema}.verification.hashes_match must be bool")
    _require(isinstance(v["files_restored"], int) and v["files_restored"] >= 0,
             f"{schema}.verification.files_restored must be non-negative int")


def validate_library(doc):
    """Validate a library/catalog document."""
    schema = "library"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "base_skills", "catalog_patterns",
        "composition_rules", "override_rules", "transfer_rules",
        "extension_rules",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, required, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")

    _require_type(doc["base_skills"], list, f"{schema}.base_skills")
    for i, bs in enumerate(doc["base_skills"]):
        prefix = f"{schema}.base_skills[{i}]"
        _require_type(bs, dict, prefix)
        _require_fields(bs, ["name", "purpose", "invariants", "scenarios",
                             "provenance"],
                        prefix)
        _reject_unknown(bs, [
            "name", "purpose", "applicability", "invariants", "limits",
            "scenarios", "provenance",
        ], prefix)
        _require(_is_nonempty_str(bs["name"]), f"{prefix}.name")
        _require_type(bs["invariants"], list, f"{prefix}.invariants")
        _require(len(bs["invariants"]) > 0,
                 f"{prefix}.invariants must not be empty")
        _require(_is_nonempty_str_list(bs["invariants"]),
                 f"{prefix}.invariants entries must be non-empty strings")
        _require_type(bs["scenarios"], list, f"{prefix}.scenarios")
        _require(len(bs["scenarios"]) > 0,
                 f"{prefix}.scenarios must not be empty: "
                 "a base skill without a tested scenario is not selectable")
        _require(_is_nonempty_str_list(bs["scenarios"]),
                 f"{prefix}.scenarios entries must be non-empty strings")
        prov = bs["provenance"]
        _require_type(prov, dict, f"{prefix}.provenance")
        _require_fields(prov, ["license", "source"], f"{prefix}.provenance")
        _reject_unknown(prov, ["license", "source", "commit", "spec_version"],
                        f"{prefix}.provenance")
        _require(_is_nonempty_str(prov["source"]),
                 f"{prefix}.provenance.source must name the origin "
                 "('internal' or a source-registry source_id)")
        _require(_is_nonempty_str(prov.get("commit"))
                 or _is_nonempty_str(prov.get("spec_version")),
                 f"{prefix}.provenance must pin commit or spec_version")

    _require_type(doc["catalog_patterns"], list,
                  f"{schema}.catalog_patterns")
    for i, cp in enumerate(doc["catalog_patterns"]):
        prefix = f"{schema}.catalog_patterns[{i}]"
        _require_type(cp, dict, prefix)
        _require_fields(cp, [
            "name", "domain", "purpose", "applicability",
            "activation_criteria", "invariants", "scenarios", "provenance",
        ], prefix)
        _reject_unknown(cp, [
            "name", "domain", "purpose", "applicability",
            "activation_criteria", "invariants", "limits", "scenarios",
            "provenance",
        ], prefix)
        _require(_is_nonempty_str(cp["name"]), f"{prefix}.name")
        _require(_is_nonempty_str(cp["domain"]), f"{prefix}.domain")
        _require(_is_nonempty_str(cp["applicability"]),
                 f"{prefix}.applicability")
        for field, label in (("activation_criteria", "activation criteria"),
                             ("invariants", "invariants"),
                             ("scenarios", "scenarios")):
            value = cp[field]
            _require_type(value, list, f"{prefix}.{field}")
            _require(len(value) > 0,
                     f"{prefix}.{field} must not be empty: a catalog pattern "
                     f"without observable {label} is not selectable")
            _require(_is_nonempty_str_list(value),
                     f"{prefix}.{field} entries must be non-empty strings")
        prov = cp["provenance"]
        _require_type(prov, dict, f"{prefix}.provenance")
        _require_fields(prov, ["license", "source"], f"{prefix}.provenance")
        _reject_unknown(prov, ["license", "source", "commit", "spec_version"],
                        f"{prefix}.provenance")
        _require(_is_nonempty_str(prov["source"]),
                 f"{prefix}.provenance.source must name the origin "
                 "('internal' or a source-registry source_id)")
        _require(_is_nonempty_str(prov.get("commit"))
                 or _is_nonempty_str(prov.get("spec_version")),
                 f"{prefix}.provenance must pin commit or spec_version")

    cr = doc["composition_rules"]
    _require_type(cr, dict, f"{schema}.composition_rules")
    _require_fields(cr, ["allowed", "constraints"],
                    f"{schema}.composition_rules")
    _reject_unknown(cr, ["allowed", "constraints", "max_composed"],
                    f"{schema}.composition_rules")

    orr = doc["override_rules"]
    _require_type(orr, dict, f"{schema}.override_rules")
    _require_fields(orr, ["allowed_slots", "forbidden_slots"],
                    f"{schema}.override_rules")
    _reject_unknown(orr, ["allowed_slots", "forbidden_slots",
                          "requires_justification"],
                    f"{schema}.override_rules")

    tr = doc["transfer_rules"]
    _require_type(tr, dict, f"{schema}.transfer_rules")
    _require_fields(tr, ["requires_acceptance", "acceptance_scope"],
                    f"{schema}.transfer_rules")
    _reject_unknown(tr, ["requires_acceptance", "acceptance_scope",
                         "source_tracking"],
                    f"{schema}.transfer_rules")
    _require(tr["requires_acceptance"] is True,
             f"{schema}.transfer_rules.requires_acceptance must be true")

    er = doc["extension_rules"]
    _require_type(er, dict, f"{schema}.extension_rules")
    _require_fields(er, ["requires_justification",
                         "must_demonstrate_no_prior_layer"],
                    f"{schema}.extension_rules")
    _reject_unknown(er, ["requires_justification",
                         "must_demonstrate_no_prior_layer",
                         "fallback_on_failure"],
                    f"{schema}.extension_rules")
    _require(er["requires_justification"] is True,
             f"{schema}.extension_rules.requires_justification must be true")
    _require(er["must_demonstrate_no_prior_layer"] is True,
             f"{schema}.extension_rules.must_demonstrate_no_prior_layer must be true")


# ---------------------------------------------------------------------------
# Source registry (external skill sources: repositories, standards, guidance)
# ---------------------------------------------------------------------------

SOURCE_KINDS = frozenset([
    "skill-repository", "catalog-index", "runtime", "standard", "guidance",
    "domain-guidance",
])

SOURCE_STATUSES = frozenset(["REFERENCE", "CANDIDATE", "ACTIVE", "REJECTED"])

SOURCE_LICENSE_STATUSES = frozenset([
    "open", "mixed", "unresolved", "proprietary", "not-applicable",
])

SOURCE_PROVENANCE_STATUSES = frozenset(["pinned", "unpinned"])

# Kinds whose material is acquired from a remote location: these always need
# an exact location, a pinned revision and a retrieval date.
SOURCE_KINDS_REQUIRING_PIN = frozenset([
    "skill-repository", "catalog-index", "runtime",
])

# Statuses that put material on the path to the library/catalog: only fully
# pinned sources with a clear-enough license may reach them.
SOURCE_STATUSES_REQUIRING_PIN = frozenset(["CANDIDATE", "ACTIVE"])

SOURCE_LICENSE_STATUSES_SELECTABLE = frozenset(["open", "mixed"])


def validate_source_registry(doc):
    """Validate the canonical source registry document."""
    schema = "source-registry"
    _require_type(doc, dict, schema)
    required = ["schema_version", "policy", "sources"]
    known = required + ["analysis_inventory"]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")

    policy = doc["policy"]
    _require_type(policy, dict, f"{schema}.policy")
    _require_fields(policy, [
        "acquisition", "auto_install_forbidden",
        "staging_outside_canonical_tree", "host_validate_before_activation",
    ], f"{schema}.policy")
    _reject_unknown(policy, [
        "acquisition", "auto_install_forbidden", "npx_marketplace_forbidden",
        "staging_outside_canonical_tree", "host_validate_before_activation",
    ], f"{schema}.policy")
    _require(_is_nonempty_str(policy["acquisition"]),
             f"{schema}.policy.acquisition")
    for constant in ("auto_install_forbidden",
                     "staging_outside_canonical_tree",
                     "host_validate_before_activation"):
        _require(policy[constant] is True,
                 f"{schema}.policy.{constant} must be true")
    if "npx_marketplace_forbidden" in policy:
        _require(policy["npx_marketplace_forbidden"] is True,
                 f"{schema}.policy.npx_marketplace_forbidden must be true")

    if "analysis_inventory" in doc:
        inv = doc["analysis_inventory"]
        _require_type(inv, dict, f"{schema}.analysis_inventory")
        _require_fields(inv, ["entries", "generated_at", "sha256"],
                        f"{schema}.analysis_inventory")
        _reject_unknown(inv, ["entries", "generated_at", "sha256", "location"],
                        f"{schema}.analysis_inventory")
        _require(isinstance(inv["entries"], int) and inv["entries"] >= 0,
                 f"{schema}.analysis_inventory.entries must be a "
                 "non-negative integer")
        _require(_is_date(inv["generated_at"]),
                 f"{schema}.analysis_inventory.generated_at must be a date")
        _require(_is_sha256(inv["sha256"]),
                 f"{schema}.analysis_inventory.sha256 must be a SHA-256")
        if "location" in inv:
            _require(_is_nonempty_str(inv["location"]),
                     f"{schema}.analysis_inventory.location")
            _require("/home/" not in inv["location"],
                     f"{schema}.analysis_inventory.location must not contain "
                     "local filesystem paths")

    sources = doc["sources"]
    _require_type(sources, list, f"{schema}.sources")
    seen_ids = set()
    for i, entry in enumerate(sources):
        prefix = f"{schema}.sources[{i}]"
        _require_type(entry, dict, prefix)
        required_entry = [
            "source_id", "title", "publisher", "kind", "provenance_status",
            "license", "license_status", "status", "decision_summary",
        ]
        known_entry = required_entry + [
            "canonical_url", "revision", "spec_version", "retrieved_at",
            "notes",
        ]
        _require_fields(entry, required_entry, prefix)
        _reject_unknown(entry, known_entry, prefix)

        sid = entry["source_id"]
        _require(_is_nonempty_str(sid), f"{prefix}.source_id")
        _require(sid not in seen_ids,
                 f"{prefix}.source_id duplicates {sid!r}")
        seen_ids.add(sid)
        _require(_is_nonempty_str(entry["title"]), f"{prefix}.title")
        _require(_is_nonempty_str(entry["publisher"]), f"{prefix}.publisher")
        _require_enum(entry["kind"], SOURCE_KINDS, f"{prefix}.kind")
        _require_enum(entry["provenance_status"],
                      SOURCE_PROVENANCE_STATUSES, f"{prefix}.provenance_status")
        _require(_is_nonempty_str(entry["license"]), f"{prefix}.license")
        _require_enum(entry["license_status"], SOURCE_LICENSE_STATUSES,
                      f"{prefix}.license_status")
        _require_enum(entry["status"], SOURCE_STATUSES, f"{prefix}.status")
        _require(_is_nonempty_str(entry["decision_summary"]),
                 f"{prefix}.decision_summary")
        _require(len(entry["decision_summary"]) <= 600,
                 f"{prefix}.decision_summary must be at most 600 characters")
        if "spec_version" in entry:
            _require(_is_nonempty_str(entry["spec_version"]),
                     f"{prefix}.spec_version")

        if "notes" in entry:
            _require(_is_nonempty_str(entry["notes"]), f"{prefix}.notes")

        needs_pin = entry["kind"] in SOURCE_KINDS_REQUIRING_PIN
        if needs_pin:
            url = entry.get("canonical_url")
            _require(_is_nonempty_str(url) and url.startswith("https://"),
                     f"{prefix}.canonical_url must be an https:// URL for "
                     f"kind={entry['kind']}")
            _require(_is_nonempty_str(entry.get("revision"))
                     and bool(_SHA256_RE.match(entry["revision"])
                              or re.match(r"^[0-9a-f]{7,64}$",
                                          entry["revision"])),
                     f"{prefix}.revision must be a pinned commit for "
                     f"kind={entry['kind']}")
            _require(_is_date(entry.get("retrieved_at")),
                     f"{prefix}.retrieved_at must be a date for "
                     f"kind={entry['kind']}")
            _require(entry["provenance_status"] == "pinned",
                     f"{prefix}.provenance_status must be 'pinned' for "
                     f"kind={entry['kind']}")

        if (entry["provenance_status"] == "pinned"
                and not needs_pin):
            _require("revision" in entry or "spec_version" in entry,
                     f"{prefix}: pinned provenance requires a revision or a "
                     "spec_version")
            if "revision" not in entry:
                _require(_is_date(entry.get("retrieved_at")),
                         f"{prefix}.retrieved_at is required when pinning a "
                         "spec_version")

        if entry["status"] in SOURCE_STATUSES_REQUIRING_PIN:
            _require(entry["provenance_status"] == "pinned",
                     f"{prefix}: status {entry['status']} requires pinned "
                     "provenance")
            _require(entry["license_status"] in
                     SOURCE_LICENSE_STATUSES_SELECTABLE,
                     f"{prefix}: status {entry['status']} requires "
                     "license_status 'open' or 'mixed', got "
                     f"{entry['license_status']!r}")


# ---------------------------------------------------------------------------
# Modes/Skills validators (shared structure with specific constraints)
# ---------------------------------------------------------------------------


def _require_reuse_reference(doc, schema):
    """Base/catalog reuse must name the exact library entry; extension must not."""
    source = doc["reuse_source"]
    ref = doc.get("reuse_reference")
    if source in ("base-library", "specialized-catalog"):
        _require(_is_nonempty_str(ref),
                 f"{schema}: reuse_reference required when reuse_source is "
                 f"{source!r}: name the exact library entry reused")
    elif source == "extension":
        _require("reuse_reference" not in doc,
                 f"{schema}: reuse_reference must be omitted when "
                 "reuse_source is 'extension'")
    else:
        _require(ref is None or _is_nonempty_str(ref),
                 f"{schema}.reuse_reference must be a non-empty string "
                 "when present")


def validate_mode_contract(doc):
    """Validate a mode contract document."""
    schema = "mode-contract"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "name", "purpose", "reuse_source", "triggers",
        "anti_triggers", "inputs", "reads", "writes",
        "required_capabilities", "forbidden_capabilities", "invariants",
        "anti_goals", "state_machine", "handoffs", "failure_modes",
        "scenarios", "provenance",
    ]
    known = required + [
        "kind", "reuse_justification", "reuse_reference", "sources", "rollback",
        "migration", "sr_criteria", "stop_conditions", "evidence",
        "entrypoint", "progressive_disclosure",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    if "kind" in doc:
        _require(doc["kind"] == "mode",
                 f"{schema}.kind: expected 'mode', got {doc['kind']!r}")
    _require(_is_nonempty_str(doc["name"]), f"{schema}.name")
    _require_enum(doc["reuse_source"], REUSE_SOURCES,
                  f"{schema}.reuse_source")
    _require_reuse_reference(doc, schema)

    if doc["reuse_source"] == "extension":
        _require("reuse_justification" in doc
                 and _is_nonempty_str(doc["reuse_justification"]),
                 f"{schema}: reuse_justification required when reuse_source is 'extension'")

    _require_type(doc["triggers"], list, f"{schema}.triggers")
    _require(len(doc["triggers"]) > 0, f"{schema}: triggers must not be empty")
    _require_type(doc["invariants"], list, f"{schema}.invariants")
    _require(len(doc["invariants"]) > 0,
             f"{schema}: invariants must not be empty")

    sm = doc["state_machine"]
    _require_type(sm, dict, f"{schema}.state_machine")
    _require_fields(sm, ["states", "transitions", "initial", "terminal"],
                    f"{schema}.state_machine")
    _reject_unknown(sm, ["states", "transitions", "initial", "terminal"],
                    f"{schema}.state_machine")
    _require_type(sm["states"], list, f"{schema}.state_machine.states")
    _require(len(sm["states"]) > 0,
             f"{schema}.state_machine.states must not be empty")

    prov = doc["provenance"]
    _require_type(prov, dict, f"{schema}.provenance")
    _require_fields(prov, ["license"], f"{schema}.provenance")
    _reject_unknown(prov, ["license", "source", "commit", "notice"],
                    f"{schema}.provenance")


def validate_skill_contract(doc):
    """Validate a skill contract document."""
    schema = "skill-contract"
    _require_type(doc, dict, schema)
    required = [
        "schema_version", "name", "motive", "domain", "reuse_source",
        "inputs", "outputs", "required_capabilities",
        "forbidden_capabilities", "files", "behavior_test", "provenance",
    ]
    known = required + [
        "kind", "evidence", "reuse_justification", "reuse_reference", "replaces",
        "prohibited_tools", "hot_paths", "load_test",
        "activation_criteria", "invariants", "anti_goals",
    ]
    _require_fields(doc, required, schema)
    _reject_unknown(doc, known, schema)
    _require(doc["schema_version"] == SCHEMA_VERSION,
             f"{schema}: unsupported schema_version")
    if "kind" in doc:
        _require(doc["kind"] == "skill",
                 f"{schema}.kind: expected 'skill', got {doc['kind']!r}")
    _require(_is_nonempty_str(doc["name"]), f"{schema}.name")
    _require(_is_nonempty_str(doc["motive"]), f"{schema}.motive")
    _require_enum(doc["reuse_source"], REUSE_SOURCES,
                  f"{schema}.reuse_source")
    _require_reuse_reference(doc, schema)

    if doc["reuse_source"] == "extension":
        _require("reuse_justification" in doc
                 and _is_nonempty_str(doc["reuse_justification"]),
                 f"{schema}: reuse_justification required when reuse_source is 'extension'")

    _require_type(doc["files"], list, f"{schema}.files")
    _require(len(doc["files"]) > 0, f"{schema}: files must not be empty")
    for i, f in enumerate(doc["files"]):
        prefix = f"{schema}.files[{i}]"
        _require_type(f, dict, prefix)
        _require_fields(f, ["path", "type"], prefix)
        _reject_unknown(f, ["path", "type", "max_bytes"], prefix)

    prov = doc["provenance"]
    _require_type(prov, dict, f"{schema}.provenance")
    _require_fields(prov, ["license"], f"{schema}.provenance")
    _reject_unknown(prov, ["license", "source", "commit", "notice"],
                    f"{schema}.provenance")


# ---------------------------------------------------------------------------
# Manifest hash verification
# ---------------------------------------------------------------------------


def compute_file_sha256(filepath):
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest_hashes(manifest_doc, generated_dir):
    """Verify that every artifact in the manifest matches its declared hash.

    Returns a list of (path, expected, actual) tuples for mismatches.
    Raises ContractError if any file is missing or if there are unmanifested
    files in generated_dir.
    """
    generated = Path(generated_dir)
    _require(generated.is_dir(),
             f"generated directory does not exist: {generated}")

    mismatches = []
    manifested_paths = set()

    for art in manifest_doc["artifacts"]:
        rel_path = art["path"]
        manifested_paths.add(rel_path)
        full_path = generated / rel_path

        _require(full_path.is_file(),
                 f"manifest artifact missing: {rel_path}")
        _require(not full_path.is_symlink(),
                 f"manifest artifact is symlink: {rel_path}")

        actual = compute_file_sha256(full_path)
        if actual != art["sha256"]:
            mismatches.append((rel_path, art["sha256"], actual))

    # Check for unmanifested files (generation-manifest.json itself is excluded)
    manifest_meta_files = {"generation-manifest.json"}
    for root, _dirs, files in os.walk(generated):
        for fname in files:
            full = Path(root) / fname
            rel = str(full.relative_to(generated))
            if rel not in manifested_paths and rel not in manifest_meta_files:
                raise ContractError(
                    f"unmanifested file in generated/: {rel}")

    return mismatches


# ---------------------------------------------------------------------------
# Path safety checks
# ---------------------------------------------------------------------------


def check_path_safety(path):
    """Reject paths with traversal, symlinks, absolute references, or specials."""
    _require(isinstance(path, str) and len(path) > 0,
             "path must be non-empty string")
    _require(not path.startswith("/"),
             f"absolute path not allowed: {path}")
    _require(".." not in path.split("/"),
             f"path traversal not allowed: {path}")
    _require("//" not in path,
             f"double slash not allowed: {path}")
    _require("\x00" not in path,
             f"null byte not allowed in path: {path!r}")


def check_no_symlinks(directory):
    """Reject a directory tree that contains any symlinks."""
    d = Path(directory)
    if not d.exists():
        return
    for item in d.rglob("*"):
        _require(not item.is_symlink(),
                 f"symlink not allowed: {item}")


def validate_discovery(doc):
    """Validate discovery claims document (§23.2)."""
    schema = "discovery"
    _require_type(doc, dict, schema)
    _require_fields(doc, ["schema_version", "project", "claims"], schema)
    _reject_unknown(doc, ["schema_version", "project", "artifact_type", "claims"], schema)
    _require(doc["schema_version"] == SCHEMA_VERSION, f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["project"]), f"{schema}.project")
    _require_type(doc["claims"], list, f"{schema}.claims")
    for i, c in enumerate(doc["claims"]):
        p = f"{schema}.claims[{i}]"
        _require_type(c, dict, p)
        _require_fields(c, ["source", "hash", "location", "state", "confidence"], p)
        _reject_unknown(c, ["source", "hash", "location", "state", "confidence", "limitations", "detail"], p)
        _require(_is_sha256(c["hash"]), f"{p}.hash must be sha256")
        _require_enum(c["state"], {"OBSERVED", "DECLARED", "INFERRED", "PROPOSED", "UNVERIFIED"}, f"{p}.state")
        _require_enum(c["confidence"], {"high", "medium", "low"}, f"{p}.confidence")


def validate_design(doc):
    """Validate design document (§24, §32)."""
    schema = "design"
    _require_type(doc, dict, schema)
    _require_fields(doc, ["schema_version", "project", "strategy", "decisions"], schema)
    _reject_unknown(doc, ["schema_version", "project", "strategy", "decisions", "capability_plan"], schema)
    _require(doc["schema_version"] == SCHEMA_VERSION, f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["project"]), f"{schema}.project")
    st = doc["strategy"]
    _require_type(st, dict, f"{schema}.strategy")
    _require_fields(st, ["selection_order", "modes"], f"{schema}.strategy")
    _reject_unknown(st, ["selection_order", "modes"], f"{schema}.strategy")
    _require(len(st["modes"]) == 2, f"{schema}.strategy.modes must have exactly 2 modes")
    _require_type(doc["decisions"], list, f"{schema}.decisions")
    for i, d in enumerate(doc["decisions"]):
        p = f"{schema}.decisions[{i}]"
        _require_type(d, dict, p)
        _require_fields(d, ["id", "subject", "resolution", "justification"], p)
        _reject_unknown(d, ["id", "subject", "resolution", "justification", "source"], p)
        _require_enum(d["resolution"], {"INFER", "ASK", "RECOMMEND", "NOT_APPLICABLE", "UNRESOLVED"}, f"{p}.resolution")


def validate_tests_spec(doc):
    """Validate holdout and test coverage specification (§26, §32)."""
    schema = "tests-spec"
    _require_type(doc, dict, schema)
    _require_fields(doc, ["schema_version", "generation_id", "families", "coverage_matrix"], schema)
    _reject_unknown(doc, ["schema_version", "generation_id", "families", "coverage_matrix", "immutable_digests"], schema)
    _require(doc["schema_version"] == SCHEMA_VERSION, f"{schema}: unsupported schema_version")
    _require(_is_nonempty_str(doc["generation_id"]), f"{schema}.generation_id")
    _require_type(doc["families"], list, f"{schema}.families")
    _require(len(doc["families"]) > 0, f"{schema}.families must not be empty")
    cm = doc["coverage_matrix"]
    _require_type(cm, dict, f"{schema}.coverage_matrix")
    _require_fields(cm, ["total_scenarios", "covered_requirements"], f"{schema}.coverage_matrix")
    _reject_unknown(cm, ["total_scenarios", "covered_requirements"], f"{schema}.coverage_matrix")
    for sr in cm["covered_requirements"]:
        _require(isinstance(sr, str) and bool(_SR_RE.match(sr)), f"{schema}.covered_requirements must match SR-N")


# ---------------------------------------------------------------------------
# Validator registry
# ---------------------------------------------------------------------------

VALIDATORS = {
    "run": validate_run,
    "generation-manifest": validate_generation_manifest,
    "project-manifest": validate_project_manifest,
    "instructions-index": validate_instructions_index,
    "capabilities": validate_capabilities,
    "scenario": validate_scenario,
    "acceptance-plan": validate_acceptance_plan,
    "handoff": validate_handoff,
    "drift": validate_drift,
    "backup": validate_backup,
    "promotion": validate_promotion,
    "rollback": validate_rollback,
    "library": validate_library,
    "source-registry": validate_source_registry,
    "mode-contract": validate_mode_contract,
    "skill-contract": validate_skill_contract,
    "discovery": validate_discovery,
    "design": validate_design,
    "tests-spec": validate_tests_spec,
}


def validate(schema_name, doc):
    """Validate a document against a named schema. Fail-closed."""
    _require(schema_name in VALIDATORS,
             f"unknown schema: {schema_name}")
    VALIDATORS[schema_name](doc)


def validate_json_file(schema_name, filepath):
    """Load a JSON file and validate against a named schema."""
    p = Path(filepath)
    _require(p.is_file(), f"file not found: {filepath}")
    _require(not p.is_symlink(), f"symlinks not allowed: {filepath}")
    with open(p, "r", encoding="utf-8") as f:
        doc = json.load(f)
    validate(schema_name, doc)
    return doc


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 -B -m scripts.generation_contracts <schema> <file>")
        print(f"Available schemas: {', '.join(sorted(VALIDATORS))}")
        sys.exit(1)

    schema_name = sys.argv[1]
    filepath = sys.argv[2]

    try:
        validate_json_file(schema_name, filepath)
        print(f"VALID: {filepath} conforms to {schema_name}")
    except ContractError as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"REJECTED: invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)
