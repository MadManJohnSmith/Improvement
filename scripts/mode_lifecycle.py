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
_LIFECYCLE_FENCE = "mode-lifecycle"


def expected_lifecycle(role, layout):
    common = {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "state_root": layout["state_root"],
        "state_schema": "state-schema.json",
        "read_before_write": True,
        "write_method": "workflow_write-full-replacement",
        "bounds": LIMITS,
    }
    if role == "auditor":
        common["audit_handoff"] = {
            "required_before_final": True,
            "dedupe_key": ["finding_id", "base_revision"],
            "writes": ["findings.jsonl", "handoffs.jsonl", "work-items.json"],
            "final_fields": ["persisted_path", "persisted_count", "next_prompt"],
            "next_prompt": "Repara los hallazgos de la auditoría; no publiques.",
        }
    elif role == "continuous-repair":
        common["repair_candidate"] = {
            "simple_prompt_authorizes": ["named-persisted", "all-persisted"],
            "canonical_preconditions": ["git-clean", "base-revision-matches"],
            "candidate_location": "sibling",
            "directory_template": f"{layout['product_root']}-repair-<base12>",
            "branch_template": "dsh/repair-<base12>",
            "provision": "git-worktree-add-or-reuse",
            "collision_policy": "retain-with-action",
            "patch_root": "candidate-only",
            "commit": "allowed-after-tests",
            "forbidden": ["canonical-product-write", "merge", "push", "publish"],
            "writes": ["work-items.json", "verification-results.jsonl", "handoffs.jsonl"],
            "final_fields": [
                "candidate_path", "candidate_branch", "candidate_commit",
                "tests", "integration_status",
            ],
            "integration_status": "ready-for-host-or-user-authorized-integration",
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


def _replace_json(path, value):
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
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
    """Create or minimally migrate the bounded mode-state files."""
    state = Path(state)
    state.mkdir(mode=0o700, exist_ok=True)
    schema = {
        "schema_version": SCHEMA_VERSION,
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
    defaults = {
        "project.json": descriptor,
        "state-schema.json": schema,
        "findings.jsonl": None,
        "handoffs.jsonl": None,
        "verification-results.jsonl": None,
    }
    for name, value in defaults.items():
        path = state / name
        if path.is_symlink():
            raise ValueError(f"mode-state file is a symlink: {path}")
        if not path.exists():
            if value is None:
                path.write_text("", encoding="utf-8")
                path.chmod(0o600)
            else:
                _replace_json(path, value)
        elif value is not None and json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError(f"mode-state file conflicts with schema: {path}")

    work_items = state / "work-items.json"
    if not work_items.exists():
        _replace_json(work_items, {"schema_version": SCHEMA_VERSION,
                                   "candidate": None, "items": []})
    else:
        current = json.loads(work_items.read_text(encoding="utf-8"))
        if isinstance(current, list):
            _replace_json(work_items, {"schema_version": SCHEMA_VERSION,
                                       "candidate": None, "items": current})
        elif not (isinstance(current, dict) and current.get("schema_version") == 1
                  and "candidate" in current and isinstance(current.get("items"), list)):
            raise ValueError("mode-state/work-items.json has an unsupported shape")
    return state
