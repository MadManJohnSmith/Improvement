"""Strict contract for Creator-controlled operational compositions."""

import json
import re
from collections import Counter


REQUIRED_MODE_PLUGINS = frozenset({
    "@deepseek-ai/dsh-persona",
    "@deepseek-ai/dsh-tool-bash",
    "@deepseek-ai/dsh-tool-fs",
    "@deepseek-ai/dsh-tool-fs-search",
    "@deepseek-ai/dsh-skill-filesystem",
    "@deepseek-ai/dsh-tool-skill",
})
PROHIBITED_MODE_PLUGIN_TERMS = (
    "delegat", "subagent", "workflow", "web", "plugin-manager",
    "plugin_manager", "pluginmanager",
)
FS_SEARCH_PLUGIN = "@deepseek-ai/dsh-tool-fs-search"
FS_SEARCH_REQUIRED_CONFIG = "sampleOverCapGlobResults"
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _scalar(value):
    value = value.strip()
    if not value:
        raise ValueError("empty scalar")
    if value[0] == value[-1] == "\"":
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError) as error:
            raise ValueError("invalid quoted scalar") from error
        if not isinstance(parsed, str):
            raise ValueError("scalar must be a string")
        return parsed
    if value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if value[0] in "'\"[{" or value[-1] in "'\"]}":
        raise ValueError("invalid scalar")
    return value


def parse_composition(path):
    """Parse the simple top-level plugin list while validating every YAML line."""
    rows = []
    current = None
    previous_indent = 0
    previous_container = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(str(error)) from error
    for number, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise ValueError(f"line {number}: tabs are not allowed")
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw[indent:]
        if indent == 0:
            match = re.fullmatch(r"-\s+id:\s*(.+?)\s*", text)
            if not match:
                raise ValueError(f"line {number}: expected top-level '- id:' row")
            current = {"id": _scalar(match.group(1)), "name": None,
                       "lines": [raw]}
            rows.append(current)
            previous_indent = 0
            previous_container = False
            continue
        if current is None or indent < 2 or indent % 2:
            raise ValueError(f"line {number}: invalid indentation")
        if indent > previous_indent + 2 or (
                previous_indent and indent > previous_indent and
                not previous_container):
            raise ValueError(f"line {number}: invalid nested structure")
        current["lines"].append(raw)
        if text.startswith("- "):
            if indent < 4 or not text[2:].strip():
                raise ValueError(f"line {number}: invalid nested list item")
            item = text[2:].strip()
            if ":" in item:
                key, value = item.split(":", 1)
                if not _KEY.fullmatch(key.strip()):
                    raise ValueError(f"line {number}: invalid nested key")
                previous_container = not value.strip()
            else:
                _scalar(item)
                previous_container = False
        else:
            if ":" not in text:
                raise ValueError(f"line {number}: unrecognized YAML")
            key, value = text.split(":", 1)
            key = key.strip()
            if not _KEY.fullmatch(key):
                raise ValueError(f"line {number}: invalid key")
            if indent == 2 and key == "id":
                raise ValueError(f"line {number}: id must start a plugin row")
            if indent == 2 and key == "name":
                if current["name"] is not None:
                    raise ValueError(f"line {number}: duplicate name field")
                current["name"] = _scalar(value)
            elif value.strip():
                _scalar(value)
            previous_container = not value.strip()
        previous_indent = indent
    if not rows:
        raise ValueError("composition must contain plugin rows")
    for row in rows:
        if row["name"] is None:
            raise ValueError(f"plugin {row['id']!r} is missing name")
    return rows


def _validate_fs_search_config(row):
    configs = 0
    values = []
    in_config = False
    for raw in row["lines"][1:]:
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw[indent:]
        if indent == 2:
            key, value = text.split(":", 1)
            in_config = key.strip() == "config" and not value.strip()
            configs += in_config
        elif in_config and indent == 4 and ":" in text:
            key, value = text.split(":", 1)
            if key.strip() == FS_SEARCH_REQUIRED_CONFIG:
                values.append(value.strip())
    setting = f"config.{FS_SEARCH_REQUIRED_CONFIG}"
    if configs != 1 or len(values) != 1:
        raise ValueError(f"plugin {FS_SEARCH_PLUGIN!r} requires {setting}: false")
    if values[0] != "false":
        raise ValueError(f"plugin {FS_SEARCH_PLUGIN!r} requires {setting} to be false")


def validate_operational_composition(path):
    rows = parse_composition(path)
    ids = Counter(row["id"] for row in rows)
    names = Counter(row["name"] for row in rows)
    duplicate_ids = sorted(value for value, count in ids.items() if count > 1)
    duplicate_names = sorted(value for value, count in names.items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"duplicate plugin ids: {duplicate_ids}")
    if duplicate_names:
        raise ValueError(f"duplicate plugin names: {duplicate_names}")
    invalid_counts = sorted(
        f"{name}={names[name]}" for name in REQUIRED_MODE_PLUGINS
        if names[name] != 1)
    if invalid_counts:
        raise ValueError(
            f"operational plugins must occur exactly once: {invalid_counts}")
    _validate_fs_search_config(next(
        row for row in rows if row["name"] == FS_SEARCH_PLUGIN))
    prohibited = sorted(
        f"{row['id']}={row['name']}" for row in rows
        if any(term in row["id"].lower() or term in row["name"].lower()
               for term in PROHIBITED_MODE_PLUGIN_TERMS))
    if prohibited:
        raise ValueError(f"prohibited plugin rows: {prohibited}")
    return rows
