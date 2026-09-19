"""Registro de piloto clean-room — C6.

No ejecuta producto ni comparte datos privados: crea un plan reproducible,
registra métricas operativas sin secretos y verifica que el workspace sea nuevo.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_new(path, value):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def create_plan(project, workspace, kind):
    project, workspace = Path(project), Path(workspace)
    if not project.is_dir() or workspace.exists():
        raise ValueError("Proyecto ausente o workspace no clean-room")
    if kind not in {"python-backend", "multipart"}:
        raise ValueError("Tipo de piloto no permitido")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "project": project.name,
        "workspace": str(workspace),
        "steps": ["install", "acceptance", "operate", "update", "uninstall"],
        "metrics": ["visible_commands", "human_decisions", "troubleshooting", "duration_seconds", "interventions"],
        "created_at": _now(),
    }


def record(plan_path, event, *, value=None, note=""):
    if any(x in note.lower() for x in ("password", "token", "secret", "api_key")):
        raise ValueError("No se permiten secretos en feedback")
    p = Path(plan_path)
    events = []
    if p.exists():
        doc = json.loads(p.read_text())
        events = doc.setdefault("events", [])
    else:
        doc = {"schema_version": SCHEMA_VERSION, "events": events}
    events.append({"event": event, "value": value, "note": note, "timestamp": _now()})
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return doc
