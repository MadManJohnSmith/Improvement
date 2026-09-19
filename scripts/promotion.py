"""Promoción y distribución de piloto — C7.

Produce un registro reproducible; no publica ni hace push sin autorización.
"""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_new(path, value):
    p = Path(path); p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write("\n")


def reconcile(run_dirs):
    runs = []
    for raw in run_dirs:
        p = Path(raw)
        if not (p / "run.json").is_file():
            raise ValueError(f"Run ausente: {p}")
        run = json.loads((p / "run.json").read_text())
        runs.append({"generation_id": run.get("generation_id"), "status": run.get("status")})
    return {"schema_version": SCHEMA_VERSION, "runs": runs, "timestamp": _now()}


def prepare(repo, *, tag=None, authorized=False):
    repo = Path(repo)
    if not (repo / ".git").is_dir():
        raise ValueError("Destino no es repositorio Git")
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
    if status.returncode != 0 or status.stdout:
        raise ValueError("Repositorio no limpio")
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("Repositorio no tiene revision HEAD") from exc
    return {"schema_version": SCHEMA_VERSION, "revision": revision, "tag": tag, "authorized": authorized, "published": False, "timestamp": _now()}


def publish(record, *, authorized=False):
    if not authorized:
        raise PermissionError("Publicación requiere autorización explícita")
    record = dict(record); record["published"] = True; record["published_at"] = _now()
    return record
