"""Exact generated-mode contract for the product/workspace sibling layout."""

import json
import re
from pathlib import Path

from mode_lifecycle import validate_mode_lifecycle
from composition_contract import validate_persona_bootstrap


_LAYOUT_BLOCK = re.compile(
    r"(?ms)^```json mode-layout\s*\n(?P<body>.*?)\n```\s*$")
_LAYOUT_KEYS = {"product_root", "workspace_root", "state_root"}


def layout_from_paths(product, workspace):
    product, workspace = Path(product), Path(workspace)
    if product.parent != workspace.parent:
        raise ValueError("product and workspace must be siblings")
    return {
        "product_root": product.name,
        "workspace_root": workspace.name,
        "state_root": f"{workspace.name}/mode-state",
    }


def validate_mode_layout(mode_dir, expected):
    """Require exact structured layout identity in mode.json and SKILL.md."""
    mode_dir = Path(mode_dir)
    mode = json.loads((mode_dir / "mode.json").read_text(encoding="utf-8"))
    if expected["product_root"] not in mode.get("reads", []):
        raise ValueError(
            f"mode.json reads must contain exact product root {expected['product_root']!r}")
    if expected["state_root"] not in mode.get("writes", []):
        raise ValueError(
            f"mode.json writes must contain exact state root {expected['state_root']!r}")

    text = (mode_dir / "SKILL.md").read_text(encoding="utf-8")
    blocks = list(_LAYOUT_BLOCK.finditer(text))
    if len(blocks) != 1:
        raise ValueError("SKILL.md must contain exactly one json mode-layout block")
    try:
        layout = json.loads(blocks[0].group("body"))
    except json.JSONDecodeError as error:
        raise ValueError(f"SKILL.md mode-layout is invalid JSON: {error}") from error
    if not isinstance(layout, dict) or set(layout) != _LAYOUT_KEYS:
        raise ValueError(
            "SKILL.md mode-layout must contain exactly product_root, "
            "workspace_root, and state_root")
    if layout != expected:
        raise ValueError(f"SKILL.md mode-layout must equal {expected!r}")
    validate_mode_lifecycle(mode_dir, expected)
    validate_persona_bootstrap(mode_dir / "agent.cordis.yml", mode_dir.name)
