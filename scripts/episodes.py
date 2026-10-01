"""Episodic memory: what was already found, fixed and proven (E2, closes F5).

The framework's most expensive failure is repetition. An auditor that meets the
same defect every session produces a finding every session, and a repairer that
tries the same fix again spends the same turn discovering it does not work.
The ledger is append-only and Host-owned; the index answers "has this signature
been closed before, and how" without loading the log, which is what makes it
usable inside a turn.

Two rules decide the shape:

* **The signature is the fingerprint, not the wording.** A defect described
  twice has to be one entry, or the memory is a second source of duplicates.
* **Only a proven repair is worth remembering.** An episode that records an
  attempt that did not verify teaches the next session to retry it, which is the
  failure this is meant to prevent. So an episode is written when a unit closes
  with a verification, and the finding alone does not earn one.
"""

import hashlib
import json
import os
from pathlib import Path
import tempfile

LEDGER_NAME = "episodes.jsonl"
INDEX_NAME = "episodes-index.json"
VERSION = 1
MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_EPISODES = 4096
MAX_REASON = 200
# How many past episodes one signature keeps. A defect fixed twice after two
# different approaches is worth two lines; a third is usually a loop.
MAX_PER_SIGNATURE = 3

VERDICTS = ("PASS", "FAIL", "BLOCKED", "NOT_COVERED")


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def signature(path, excerpt, fingerprint=None):
    """A stable identity for a defect: its fingerprint when the tool gave one,
    otherwise the same pair the fingerprint is computed from."""
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    if not isinstance(path, str) or not isinstance(excerpt, str):
        raise ValueError("firma de episodio necesita ruta y fragmento")
    return _digest(f"{path}\n{excerpt}")


def _checked(workspace):
    workspace = Path(workspace)
    state = workspace / "mode-state"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    return state


def ledger_path(workspace):
    return _checked(workspace) / LEDGER_NAME


def index_path(workspace):
    return _checked(workspace) / INDEX_NAME


def _text(value, label, limit=MAX_REASON):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} debe ser texto no vacío")
    if len(value) > limit:
        raise ValueError(f"{label} excede {limit} bytes")
    return value


def _read_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as error:
        raise ValueError(f"{path} ilegible: {error}") from error
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise ValueError(f"{path} con versión desconocida")
    return value


def read_index(workspace):
    index = _read_json(index_path(workspace), {"version": VERSION, "signatures": {}})
    if not isinstance(index.get("signatures"), dict):
        raise ValueError("índice de episodios con forma inesperada")
    return index


def record(workspace, *, unit, path, excerpt, verdict, evidence, repair=None,
           fingerprint=None):
    """Close one episode. Only a verified repair is worth the entry."""
    if verdict not in VERDICTS:
        raise ValueError(f"veredicto inválido: {verdict!r}")
    if verdict != "PASS":
        raise ValueError(
            "un intento no verificado no se recuerda: repetirlo es el fallo que "
            "este registro existe para evitar")
    episode = {
        "version": VERSION,
        "unit": _text(unit, "unit", 128),
        "signature": signature(path, excerpt, fingerprint),
        "path": _text(path, "path", 512),
        "verdict": verdict,
        "evidence": _text(evidence, "evidence", 1024),
        "repair": None if repair is None else _text(repair, "repair", 1024),
    }
    ledger = ledger_path(workspace)
    if ledger.exists() and ledger.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("el registro de episodios supera el tope de disco")
    # Append in place, never replace: a temp file plus os.replace would drop
    # every earlier episode, which is the opposite of what a ledger is for.
    # O_APPEND puts the line at the end atomically; a crash can still leave a
    # partial last line, which read_episodes skips rather than fails on.
    handle = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(handle, (json.dumps(episode, ensure_ascii=False, sort_keys=True)
                          + "\n").encode("utf-8"))
        os.fsync(handle)
    finally:
        os.close(handle)
    _reindex(workspace, episode)
    return episode


def read_episodes(workspace):
    """Every episode, skipping a trailing line a crash left half-written."""
    try:
        text = ledger_path(workspace).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    records = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            if index == len(text.splitlines()) - 1:
                continue  # a partial last line is a crash, not corruption
            raise ValueError("el registro de episodios tiene una línea inválida")
        records.append(value)
    return records


def _reindex(workspace, episode):
    index = read_index(workspace)
    entries = index["signatures"].setdefault(episode["signature"], [])
    entries.append({"unit": episode["unit"], "verdict": episode["verdict"],
                    "evidence": episode["evidence"], "repair": episode["repair"]})
    del entries[:-MAX_PER_SIGNATURE]
    index["signatures"] = dict(sorted(index["signatures"].items()))
    path = index_path(workspace)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent,
                                         text=True)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def recall(workspace, path=None, excerpt=None, fingerprint=None, limit=3):
    """What is already known, answered from the index and not from the log."""
    if fingerprint is not None and (path is None or excerpt is None):
        found = read_index(workspace)["signatures"].get(fingerprint, [])
    else:
        if path is None and fingerprint is None:
            raise ValueError("recall necesita firma o ruta y fragmento")
        found = read_index(workspace)["signatures"].get(
            signature(path, excerpt or "", fingerprint), [])
    return found[-limit:] if limit else found


def is_repeat(workspace, path, excerpt, fingerprint=None):
    """True when this defect already has a proven fix. The auditor asks this
    before persisting, so a repeat is marked with its episode instead of
    re-raised as new work."""
    return bool(recall(workspace, path, excerpt, fingerprint, limit=1))


def stats(workspace):
    index = read_index(workspace)
    ledger = ledger_path(workspace)
    return {
        "signatures": len(index["signatures"]),
        "episodes": sum(len(v) for v in index["signatures"].values()),
        "ledger_bytes": ledger.stat().st_size if ledger.exists() else 0,
    }
