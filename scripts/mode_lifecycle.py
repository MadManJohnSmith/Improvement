"""Versioned lifecycle contract and bounded shared state for generated modes."""

import hashlib
import json
import os
import re
import shlex
import shutil
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
LEGACY_FILE_BYTE_LIMIT = 8 * 1024 * 1024
LEGACY_TOTAL_BYTE_LIMIT = 32 * 1024 * 1024
LEGACY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LIFECYCLE_FENCE = "mode-lifecycle"


def startup_check(layout):
    return ("pwd && test \"$(basename \"$PWD\")\" = "
            f"{shlex.quote(layout['session_root'])}"
            f" && test -d ./{shlex.quote(layout['product_root'])}"
            f" && test -d ./{shlex.quote(layout['workspace_root'])}")


def persona_prefix(preset_id):
    return (f"Preset bootstrap: your first action MUST call the skill tool with exact skill "
            f"{preset_id!r}. Do not analyze, use another tool, or answer before that call "
            "succeeds. If loading fails, stop and report RETAINED. After the skill succeeds, "
            "the first bash call MUST omit workdir (or use exactly '.') and run exactly the "
            "pwd and relative layout checks declared by mode-lifecycle (startup_workdir: "
            "session-cwd-only; workdir_override: forbidden-before-layout). Never infer, climb, "
            "cd, or otherwise change workdir to validate layout. Resolve every later relative "
            "path from the observed unchanged session cwd; any pwd drift is RETAINED.")


def expected_lifecycle(role, layout):
    common = {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "state_root": layout["state_root"],
        "state_schema": "state-schema.json",
        "read_before_write": True,
        "write_method": "workflow_write-full-replacement-not-atomic",
        "bounds": LIMITS,
        "startup": {
            "startup_workdir": "session-cwd-only",
            "workdir_override": "forbidden-before-layout",
            "first_post_skill_tool": "bash",
            "first_bash_workdir": "omitted-or-dot",
            "first_bash_command": startup_check(layout),
            "expected_cwd_basename": layout["session_root"],
            "relative_layout_checks": [
                f"./{layout['product_root']}", f"./{layout['workspace_root']}"],
            "path_resolution": "observed-unchanged-session-cwd",
            "pwd_drift": "RETAINED",
        },
        "tool_policy": {
            "session_workdir": "observed-unchanged-session-cwd",
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
        startup = value.get("startup", {})
        checks = startup.get("relative_layout_checks", [])
        if not isinstance(checks, list) or len(checks) != 2:
            raise ValueError("mode_lifecycle startup requires two relative layout checks")
        product_root = checks[0][2:] if isinstance(checks[0], str) and checks[0].startswith("./") else None
        workspace_root = state_root.rsplit("/mode-state", 1)[0]
        session_root = startup.get("expected_cwd_basename")
        layout = {"session_root": session_root, "state_root": state_root,
                  "product_root": product_root, "workspace_root": workspace_root}
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


def _is_valid(value, schema, label):
    try:
        _valid(value, schema, label)
        return True
    except ValueError:
        return False


def _adapt_record(record, spec, label):
    if _is_valid(record, spec["record"], label):
        return record, False
    if (label.startswith("findings.jsonl:") and isinstance(record, dict) and
            "finding_id" not in record and set(record) == {
                "id", "base_revision", "severity", "summary", "status"}):
        adapted = {"finding_id": record["id"], **{
            key: value for key, value in record.items() if key != "id"}}
        if _is_valid(adapted, spec["record"], label):
            return adapted, True
    return None, True


def _jsonl(data, spec, label):
    records = []
    incompatible = False
    for number, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        if len(raw) > RECORD_BYTE_LIMIT:
            incompatible = True
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            incompatible = True
            continue
        record, changed = _adapt_record(record, spec, f"{label}:{number}")
        incompatible |= changed
        if record is not None:
            records.append(record)
    compacted = compact_records(records, spec["dedupe_key"], spec["limit"])
    encoded = b"".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n" for record in compacted)
    return encoded, incompatible


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


def _legacy_inventory(entries, metadata):
    return [{"name": name, **metadata[name],
             "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in sorted(entries.items())]


def _verified_legacy_archive(root, digest, inventory, descriptor):
    destination = root / digest
    if not destination.is_dir() or destination.is_symlink():
        return False
    try:
        receipt = json.loads((destination / "receipt.json").read_bytes())
        recorded = json.loads((destination / "inventory.json").read_bytes())
    except (OSError, json.JSONDecodeError):
        return False
    if (recorded != inventory or receipt.get("schema_version") != 1 or
            receipt.get("set_sha256") != digest or receipt.get("files") != inventory or
            receipt.get("state_root") != descriptor.get("state_root")):
        return False
    files = destination / "files"
    if not files.is_dir() or files.is_symlink():
        return False
    try:
        return ({entry.name for entry in files.iterdir()} ==
                {item["name"] for item in inventory} and
                all(hashlib.sha256(_preflight_file(
                    files / item["name"], LEGACY_FILE_BYTE_LIMIT)).hexdigest() ==
                    item["sha256"] for item in inventory))
    except (OSError, ValueError):
        return False


def _archive_legacy(entries, metadata, descriptor, archive_root):
    inventory = _legacy_inventory(entries, metadata)
    digest = hashlib.sha256(_encode_json(inventory)).hexdigest()
    root = Path(archive_root)
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise ValueError(f"unsafe legacy mode-state archive root: {root}")
    destination = root / digest
    if destination.exists():
        if not _verified_legacy_archive(root, digest, inventory, descriptor):
            raise ValueError(f"legacy mode-state archive conflicts or is damaged: {destination}")
        return destination

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=root))
    published = False
    try:
        files = stage / "files"
        files.mkdir(mode=0o700)
        for name, data in entries.items():
            _replace_bytes(files / name, data)
        _replace_bytes(stage / "inventory.json", _encode_json(inventory))
        _replace_bytes(stage / "receipt.json", _encode_json({
            "schema_version": 1,
            "set_sha256": digest,
            "state_root": descriptor.get("state_root"),
            "files": inventory,
            "file_count": len(inventory),
            "total_bytes": sum(item["size"] for item in inventory),
            "limits": {"per_file_bytes": LEGACY_FILE_BYTE_LIMIT,
                       "total_bytes": LEGACY_TOTAL_BYTE_LIMIT},
        }))
        stage.rename(destination)
        published = True
        if not _verified_legacy_archive(root, digest, inventory, descriptor):
            raise ValueError(f"legacy mode-state archive verification failed: {destination}")
    except BaseException:
        cleanup = destination if published else stage
        if cleanup.exists():
            shutil.rmtree(cleanup)
        raise
    return destination


def initialize_state(state, descriptor, archive_root=None):
    """Preflight state, archive bounded legacy evidence, then migrate strict files."""
    state = Path(state)
    if state.exists():
        if not state.is_dir() or state.is_symlink():
            raise ValueError(f"unsafe mode-state root: {state}")
    allowed = {"project.json", "state-schema.json", *LIMITS}
    existing = set()
    legacy = {}
    legacy_metadata = {}
    if state.exists():
        existing = {entry.name for entry in state.iterdir()}
        for name in existing - allowed:
            if not LEGACY_NAME.fullmatch(name):
                raise ValueError(f"unsafe legacy mode-state name: {name!r}")
            legacy[name] = _preflight_file(state / name, LEGACY_FILE_BYTE_LIMIT)
            legacy_metadata[name] = {"source_path": name, "reason": "unexpected-evidence"}

    schema = state_schema()
    staged = {"project.json": _encode_json(descriptor), "state-schema.json": _encode_json(schema)}
    originals = {}

    def preserve_expected(name, data, reason):
        archive_name = f"active-{name}"
        if archive_name in legacy:
            archive_name = f"active-{hashlib.sha256(name.encode()).hexdigest()[:16]}-{name}"
        legacy[archive_name] = data
        legacy_metadata[archive_name] = {"source_path": name, "reason": reason}
    for name in existing & allowed:
        data = _preflight_file(state / name, LEGACY_FILE_BYTE_LIMIT)
        originals[name] = data
        if name == "project.json":
            try:
                project = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                project = None
            if project != descriptor:
                if (isinstance(project, dict) and
                        {key: project.get(key) for key in descriptor} == descriptor):
                    preserve_expected(name, data, "legacy-equivalent-descriptor")
                else:
                    raise ValueError(f"mode-state file conflicts with descriptor: {state / name}")
        if len(data) > BYTE_LIMITS[name]:
            preserve_expected(name, data, "oversized-incompatible-expected-file")
            continue
        if name == "state-schema.json":
            try:
                stored_schema = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                stored_schema = None
            if stored_schema not in (schema, _legacy_state_schema()):
                preserve_expected(name, data, "incompatible-expected-file")
        if name.endswith(".jsonl"):
            staged[name], incompatible = _jsonl(data, schema["files"][name], name)
            if incompatible:
                preserve_expected(name, data, "incompatible-records")
        if name == "work-items.json":
            incompatible = False
            try:
                current = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                current = None
                incompatible = True
            if isinstance(current, list):
                current = {"schema_version": SCHEMA_VERSION, "candidate": None, "items": current}
                incompatible = True
            elif isinstance(current, dict) and set(current) == {"candidate", "items"}:
                current = {"schema_version": SCHEMA_VERSION, **current}
                incompatible = True
            if not (isinstance(current, dict) and set(current) == {"schema_version", "candidate", "items"}
                    and current["schema_version"] == SCHEMA_VERSION and isinstance(current["items"], list)):
                current = {"schema_version": SCHEMA_VERSION, "candidate": None, "items": []}
                incompatible = True
            else:
                item_spec = schema["files"][name]["item"]
                items = []
                for index, item in enumerate(current["items"]):
                    if (len(json.dumps(item, ensure_ascii=False).encode()) <= RECORD_BYTE_LIMIT and
                            _is_valid(item, item_spec, f"work-items.json.items[{index}]")):
                        items.append(item)
                    else:
                        incompatible = True
                candidate_spec = schema["files"][name]["candidate"]
                if not _is_valid(current["candidate"], candidate_spec, "work-items.json.candidate"):
                    current["candidate"] = None
                    incompatible = True
                current["items"] = compact_records(items, ("work_item_id", "base_revision"), LIMITS[name])
            staged[name] = _encode_json(current)
            if incompatible:
                preserve_expected(name, data, "legacy-or-incompatible-work-items")

    for name in LIMITS:
        if name not in staged:
            staged[name] = (_encode_json({"schema_version": 1, "candidate": None, "items": []})
                            if name == "work-items.json" else b"")
        if len(staged[name]) > BYTE_LIMITS[name]:
            raise ValueError(f"compacted mode-state file remains oversized: {name}")

    legacy_total = sum(map(len, legacy.values()))
    if legacy_total > LEGACY_TOTAL_BYTE_LIMIT:
        raise ValueError(
            f"legacy mode-state evidence exceeds total cap of {LEGACY_TOTAL_BYTE_LIMIT} bytes")
    if legacy:
        if archive_root is None:
            raise ValueError("legacy mode-state evidence requires a managed archive root")
        _archive_legacy(legacy, legacy_metadata, descriptor, archive_root)
    state.mkdir(mode=0o700, exist_ok=True)
    removed = []
    try:
        removals = {metadata["source_path"]: originals.get(metadata["source_path"], legacy[name])
                    for name, metadata in legacy_metadata.items()}
        for name, data in removals.items():
            path = state / name
            if _preflight_file(path, LEGACY_FILE_BYTE_LIMIT) != data:
                raise ValueError(f"legacy mode-state file changed during migration: {path}")
            path.unlink()
            removed.append((path, data))
        for name, encoded in staged.items():
            _replace_bytes(state / name, encoded)
    except BaseException:
        for name in staged:
            path = state / name
            if name in originals:
                _replace_bytes(path, originals[name])
            elif path.exists():
                path.unlink()
        for path, data in removed:
            if not path.exists():
                _replace_bytes(path, data)
        raise
    return state
