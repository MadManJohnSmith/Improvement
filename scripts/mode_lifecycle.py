"""Versioned lifecycle contract and bounded shared state for generated modes."""

import json
import os
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
LIMITS = {
    "findings.jsonl": 200,
    "handoffs.jsonl": 50,
    "work-items.json": 200,
    "verification-results.jsonl": 200,
}
BYTE_LIMITS = {
    "project.json": 8_192,
    "state-schema.json": 32_768,
    "findings.jsonl": 262_144,
    "handoffs.jsonl": 131_072,
    "work-items.json": 262_144,
    "verification-results.jsonl": 262_144,
}
RECORD_BYTE_LIMIT = 4_096
_LIFECYCLE_FENCE = "mode-lifecycle"


def persona_prefix(preset_id):
    return (f"Preset bootstrap: your first action MUST call the skill tool with exact skill "
            f"{preset_id!r}. Do not analyze, use another tool, or answer before that call "
            "succeeds. If loading fails, stop and report RETAINED.")


def expected_lifecycle(role, layout):
    common = {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "state_root": layout["state_root"],
        "state_schema": "state-schema.json",
        "read_before_write": True,
        "write_method": "workflow_write-full-replacement-not-atomic",
        "bounds": LIMITS,
        "tool_policy": {
            "session_workdir": "common-parent",
            "state_writes": {"tool": "workflow_write", "root": layout["state_root"]},
            "write_edit_tools": "forbidden",
        },
    }
    if role == "auditor":
        common["tool_policy"]["bash"] = "read-only"
        common["audit_handoff"] = {
            "required_before_final": True,
            "dedupe_key": ["finding_id", "base_revision"],
            "writes": ["findings.jsonl", "handoffs.jsonl", "work-items.json"],
            "final_fields": ["persisted_path", "persisted_count", "next_prompt"],
            "next_prompt": "Repara los hallazgos de la auditoría; no publiques.",
        }
    elif role == "continuous-repair":
        common["tool_policy"]["bash"] = "code-changes-require-workdir-exact-candidate"
        common["repair_candidate"] = {
            "simple_prompt_authorizes": ["named-persisted", "all-persisted"],
            "simple_prompt_does_not_authorize": ["commit", "merge", "push", "publish"],
            "canonical_invariant": {
                "capture_before": ["HEAD", "status-porcelain-v1"],
                "verify_after_each_phase": True,
                "on_drift": "RETAINED-no-further-action",
            },
            "candidate_location": "sibling",
            "identity": "sha256(full-base-lf-sorted-unique-finding-ids)",
            "directory_template": f"{layout['product_root']}-repair-<digest16>",
            "branch_template": "dsh/repair-<digest16>",
            "provision_checks": [
                "canonical-real-directory-not-symlink", "canonical-git-clean",
                "full-base-revision-matches", "candidate-path-absent-or-real-directory-not-symlink",
                "candidate-listed-worktree-if-present", "branch-absent-or-head-equals-full-base",
                "candidate-head-equals-full-base-on-reuse", "candidate-clean-on-reuse",
                "no-stale-prunable-worktree", "no-path-branch-worktree-collision",
            ],
            "provision": "git-worktree-add-or-exact-safe-reuse",
            "collision_policy": "retain-with-action-no-improvisation",
            "patch_root": "candidate-only",
            "candidate_diff_check": "git-diff-from-full-base-candidate-only",
            "commit": "forbidden-without-separate-explicit-user-prompt",
            "forbidden": ["canonical-product-write", "write-tool", "edit-tool", "merge", "push", "publish"],
            "writes": ["work-items.json", "verification-results.jsonl", "handoffs.jsonl"],
            "final_fields": [
                "candidate_path", "candidate_branch", "candidate_commit",
                "tests", "integration_status",
            ],
            "candidate_commit_nullable": True,
            "integration_status": "dirty-candidate-or-patch-awaiting-user-authorized-integration",
        }
    else:
        raise ValueError(f"unsupported mode role: {role!r}")
    return common


def lifecycle_block(document):
    marker = f"```json {_LIFECYCLE_FENCE}\n"
    parts = document.split(marker)
    if len(parts) != 2:
        raise ValueError("SKILL.md must contain exactly one json mode-lifecycle block")
    body, suffix = parts[1].split("\n```", 1) if "\n```" in parts[1] else (None, None)
    if body is None or marker in suffix:
        raise ValueError("SKILL.md mode-lifecycle block is malformed")
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError(f"SKILL.md mode-lifecycle is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("SKILL.md mode-lifecycle must be an object")
    return value


def validate_lifecycle_contract(value, role, layout=None):
    if not isinstance(value, dict):
        raise ValueError("mode_lifecycle must be an object")
    if layout is None:
        state_root = value.get("state_root")
        if not isinstance(state_root, str) or not state_root.endswith("/mode-state"):
            raise ValueError("mode_lifecycle state_root must end in /mode-state")
        product_root = value.get("repair_candidate", {}).get("directory_template", "").split("-repair-", 1)[0]
        if role == "auditor":
            product_root = "<product>"
        layout = {"state_root": state_root, "product_root": product_root}
    expected = expected_lifecycle(role, layout)
    if value != expected:
        raise ValueError("mode_lifecycle does not match the role contract")


def validate_mode_lifecycle(mode_dir, expected_layout):
    mode_dir = Path(mode_dir)
    mode = json.loads((mode_dir / "mode.json").read_text(encoding="utf-8"))
    expected = expected_lifecycle(mode.get("role"), expected_layout)
    if mode.get("mode_lifecycle") != expected:
        raise ValueError("mode.json mode_lifecycle does not match the role contract")
    skill = (mode_dir / "SKILL.md").read_text(encoding="utf-8")
    if lifecycle_block(skill) != expected:
        raise ValueError("SKILL.md mode-lifecycle does not match the role contract")


def compact_records(records, key_fields, limit):
    """Keep the newest record per key, then the newest bounded records."""
    if not isinstance(records, list) or not isinstance(limit, int) or limit < 1:
        raise ValueError("invalid compaction input")
    latest = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("state records must be objects")
        try:
            key = tuple(record[field] for field in key_fields)
        except KeyError as error:
            raise ValueError(f"state record missing dedupe field: {error.args[0]}") from error
        if key in latest:
            del latest[key]
        latest[key] = record
    return list(latest.values())[-limit:]


def _record_schema(required, properties, example):
    return {"type": "object", "required": required, "additionalProperties": False,
            "properties": properties, "example": example, "max_bytes": RECORD_BYTE_LIMIT}


def _legacy_state_schema():
    return {
        "schema_version": 1,
        "files": {
            "findings.jsonl": {"format": "jsonl", "limit": LIMITS["findings.jsonl"],
                               "dedupe_key": ["finding_id", "base_revision"]},
            "handoffs.jsonl": {"format": "jsonl", "limit": LIMITS["handoffs.jsonl"],
                               "dedupe_key": ["handoff_id", "base_revision"]},
            "work-items.json": {"format": "object", "limit": LIMITS["work-items.json"],
                                "items_key": "items", "candidate_key": "candidate"},
            "verification-results.jsonl": {
                "format": "jsonl", "limit": LIMITS["verification-results.jsonl"],
                "dedupe_key": ["finding_id", "candidate_commit"],
            },
        },
    }


def state_schema():
    text = {"type": "string", "minLength": 1, "maxLength": 1024}
    revision = {"type": "string", "pattern": "^[0-9a-f]{40,64}$"}
    return {
        "schema_version": SCHEMA_VERSION,
        "record_max_bytes": RECORD_BYTE_LIMIT,
        "files": {
            "findings.jsonl": {"format": "jsonl", "limit": LIMITS["findings.jsonl"],
                "max_bytes": BYTE_LIMITS["findings.jsonl"], "dedupe_key": ["finding_id", "base_revision"],
                "record": _record_schema(["finding_id", "base_revision", "severity", "summary", "status"],
                    {"finding_id": text, "base_revision": revision, "severity": {"enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]}, "summary": text, "status": {"enum": ["OPEN", "RESOLVED", "RETAINED"]}},
                    {"finding_id": "A-01", "base_revision": "a" * 40, "severity": "HIGH", "summary": "Missing validation", "status": "OPEN"})},
            "handoffs.jsonl": {"format": "jsonl", "limit": LIMITS["handoffs.jsonl"],
                "max_bytes": BYTE_LIMITS["handoffs.jsonl"], "dedupe_key": ["handoff_id", "base_revision"],
                "record": _record_schema(["handoff_id", "base_revision", "finding_ids", "next_prompt"],
                    {"handoff_id": text, "base_revision": revision, "finding_ids": {"type": "array", "items": text, "maxItems": 200}, "next_prompt": text},
                    {"handoff_id": "audit-1", "base_revision": "a" * 40, "finding_ids": ["A-01"], "next_prompt": "Repara A-01; no publiques."})},
            "work-items.json": {"format": "object", "limit": LIMITS["work-items.json"],
                "max_bytes": BYTE_LIMITS["work-items.json"], "items_key": "items", "candidate_key": "candidate",
                "item": _record_schema(["work_item_id", "finding_id", "base_revision", "status"],
                    {"work_item_id": text, "finding_id": text, "base_revision": revision, "status": {"enum": ["PENDING", "IN_PROGRESS", "VERIFIED", "RETAINED"]}},
                    {"work_item_id": "W-01", "finding_id": "A-01", "base_revision": "a" * 40, "status": "PENDING"}),
                "candidate": {"type": ["object", "null"], "required": ["base_revision", "finding_ids_digest", "path", "branch", "head", "status"], "additionalProperties": False,
                    "properties": {"base_revision": revision, "finding_ids_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "path": {"type": "string", "pattern": "^[^/][^\\0]*$"}, "branch": {"type": "string", "pattern": "^dsh/repair-[0-9a-f]{16}$"}, "head": revision, "status": {"enum": ["DIRTY", "PATCH_READY", "RETAINED"]}},
                    "example": {"base_revision": "a" * 40, "finding_ids_digest": "b" * 64, "path": "Product-repair-bbbbbbbbbbbbbbbb", "branch": "dsh/repair-bbbbbbbbbbbbbbbb", "head": "a" * 40, "status": "DIRTY"}}},
            "verification-results.jsonl": {"format": "jsonl", "limit": LIMITS["verification-results.jsonl"],
                "max_bytes": BYTE_LIMITS["verification-results.jsonl"], "dedupe_key": ["finding_id", "candidate_head"],
                "record": _record_schema(["finding_id", "candidate_head", "result", "command"],
                    {"finding_id": text, "candidate_head": revision, "result": {"enum": ["PASS", "FAIL", "BLOCKED"]}, "command": text},
                    {"finding_id": "A-01", "candidate_head": "a" * 40, "result": "PASS", "command": "pytest"})},
        },
    }


def _valid(value, schema, label):
    types = schema.get("type")
    if types:
        choices = types if isinstance(types, list) else [types]
        mapping = {"object": dict, "array": list, "string": str, "null": type(None)}
        if not any(type(value) is mapping[kind] for kind in choices):
            raise ValueError(f"{label} has invalid type")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 30):
            raise ValueError(f"{label} has invalid length")
        import re
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{label} has invalid format")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} has invalid value")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", 1 << 30):
            raise ValueError(f"{label} has too many items")
        for index, item in enumerate(value):
            _valid(item, schema.get("items", {}), f"{label}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if any(key not in value for key in required):
            raise ValueError(f"{label} missing required fields")
        if schema.get("additionalProperties") is False and set(value) - set(schema.get("properties", {})):
            raise ValueError(f"{label} has unknown fields")
        for key, item in value.items():
            _valid(item, schema.get("properties", {}).get(key, {}), f"{label}.{key}")


def _encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _preflight_file(path, max_bytes):
    stat = path.lstat()
    if not path.is_file() or path.is_symlink() or stat.st_nlink != 1:
        raise ValueError(f"unsafe mode-state file: {path}")
    if stat.st_size > max_bytes:
        raise ValueError(f"oversized mode-state file: {path}")
    return path.read_bytes()


def _jsonl(data, spec, label):
    records = []
    for number, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        if len(raw) > RECORD_BYTE_LIMIT:
            raise ValueError(f"{label}:{number} record is oversized")
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"{label}:{number} malformed JSON") from error
        _valid(record, spec["record"], f"{label}:{number}")
        records.append(record)
    compacted = compact_records(records, spec["dedupe_key"], spec["limit"])
    return b"".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n" for record in compacted)


def _replace_bytes(path, encoded):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def initialize_state(state, descriptor):
    """Preflight all existing state, then compact/migrate it without partial validation writes."""
    state = Path(state)
    if state.exists():
        if not state.is_dir() or state.is_symlink():
            raise ValueError(f"unsafe mode-state root: {state}")
    allowed = {"project.json", "state-schema.json", *LIMITS}
    existing = set()
    if state.exists():
        existing = {entry.name for entry in state.iterdir()}
        if existing - allowed:
            raise ValueError(f"unexpected mode-state entries: {sorted(existing - allowed)}")

    schema = state_schema()
    staged = {"project.json": _encode_json(descriptor), "state-schema.json": _encode_json(schema)}
    for name in existing:
        data = _preflight_file(state / name, BYTE_LIMITS[name])
        if name == "project.json" and json.loads(data) != descriptor:
            raise ValueError(f"mode-state file conflicts with descriptor: {state / name}")
        if name == "state-schema.json" and json.loads(data) not in (schema, _legacy_state_schema()):
            raise ValueError(f"mode-state file conflicts with schema: {state / name}")
        if name.endswith(".jsonl"):
            staged[name] = _jsonl(data, schema["files"][name], name)
        if name == "work-items.json":
            try:
                current = json.loads(data)
            except json.JSONDecodeError as error:
                raise ValueError("mode-state/work-items.json malformed JSON") from error
            if isinstance(current, list):
                current = {"schema_version": SCHEMA_VERSION, "candidate": None, "items": current}
            if not (isinstance(current, dict) and set(current) == {"schema_version", "candidate", "items"}
                    and current["schema_version"] == SCHEMA_VERSION and isinstance(current["items"], list)):
                raise ValueError("mode-state/work-items.json has an unsupported shape")
            item_spec = schema["files"][name]["item"]
            for index, item in enumerate(current["items"]):
                if len(json.dumps(item, ensure_ascii=False).encode()) > RECORD_BYTE_LIMIT:
                    raise ValueError(f"work-items.json item {index} is oversized")
                _valid(item, item_spec, f"work-items.json.items[{index}]")
            _valid(current["candidate"], schema["files"][name]["candidate"], "work-items.json.candidate")
            current["items"] = compact_records(current["items"], ("work_item_id", "base_revision"), LIMITS[name])
            staged[name] = _encode_json(current)

    for name in LIMITS:
        if name not in staged:
            staged[name] = (_encode_json({"schema_version": 1, "candidate": None, "items": []})
                            if name == "work-items.json" else b"")
        if len(staged[name]) > BYTE_LIMITS[name]:
            raise ValueError(f"compacted mode-state file remains oversized: {name}")
    state.mkdir(mode=0o700, exist_ok=True)
    for name, encoded in staged.items():
        _replace_bytes(state / name, encoded)
    return state
