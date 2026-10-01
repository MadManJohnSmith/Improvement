"""Write-ahead commit marker for the managed state (E1, closes D1).

`mode-state` is five files, and replacing them is five writes. A crash in the
middle leaves a state where `findings.jsonl` says one thing and `work-items.json`
says another, and the framework has no way to notice: the next run reads both and
believes them.

Full multi-file atomicity would require storing the state in a single file,
which would put the whole log on the hot path of every read. That is a worse
trade than the problem. What is worth buying is *detection and recovery*: a
marker that names what was in flight, written before the first write of a unit
and removed when the unit closes. A marker found at startup means the unit
landed partially, and the framework says so by name instead of reading a torn
state as truth.

The marker is the Host's, not the mode's. A mode that could write or clear it
could also fake a clean state, which is exactly the property this buys.
"""

import json
import os
from pathlib import Path
import tempfile

MARKER_NAME = ".commit.json"
MARKER_VERSION = 1
MAX_ENTRIES = 64
# How long a marker may sit before it is treated as abandoned rather than as a
# unit still in flight. A unit that legitimately takes longer than this is
# reported as interrupted, which is the safe direction: work redone is cheap,
# a torn state believed to be whole is not.
ABANDONED_AFTER_SECONDS = 3600

_RECOVERABLE = ("OSError", "ValueError", "TypeError", "KeyError")


def marker_path(state_root):
    return Path(state_root) / MARKER_NAME


def _digest(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise ValueError(f"marcador de commit ilegible: {error}") from error
    if not isinstance(value, dict) or value.get("version") != MARKER_VERSION:
        raise ValueError("marcador de commit con versión desconocida")
    return value


def _write(path, value):
    """Atomic replace, so a crash never leaves a half-written marker."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent,
                                         text=True)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
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
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def open_commit(state_root, unit, session=None, now=None):
    """Record a unit as in flight. Overwrites an older marker rather than nesting.

    A marker that already exists means a previous unit never closed. Replacing
    it loses the name of that unit, so the caller is expected to have reconciled
    first; `reconcile` is what decides that, and refusing to nest would make the
    common case -- a crashed unit followed by a retry -- impossible to start.
    """
    state_root = Path(state_root)
    entries = read_commit(state_root)
    if entries is not None and entries.get("unit") == unit:
        return entries
    marker = {
        "version": MARKER_VERSION,
        "unit": unit,
        "session": session,
        "opened_at": now if now is not None else 0,
        "files": [],
    }
    _write(marker_path(state_root), marker)
    return marker


def record_write(state_root, relative, content):
    """Name a file that has just landed, with the digest it landed as."""
    state_root = Path(state_root)
    marker = _read(marker_path(state_root))
    if marker is None:
        raise ValueError("escritura gestionada sin marcador de commit abierto")
    files = [item for item in marker["files"] if item["path"] != relative]
    if len(files) >= MAX_ENTRIES:
        raise ValueError(f"la unidad toca más de {MAX_ENTRIES} ficheros de estado")
    files.append({"path": relative, "sha256": _digest(content.encode("utf-8"))})
    marker["files"] = sorted(files, key=lambda item: item["path"])
    _write(marker_path(state_root), marker)
    return marker


def close_commit(state_root):
    """The unit finished: its writes are whole, so the marker has nothing to say."""
    path = marker_path(state_root)
    if _read(path) is None:
        return False
    path.unlink()
    return True


def read_commit(state_root):
    return _read(marker_path(state_root))


def reconcile(state_root, now=None):
    """Name the unit that landed partially, or say there was none.

    Returns a report the caller can surface. A marker whose files are all present
    with the digests they were written as is a unit that finished writing and
    died before closing: the state is whole, and saying so is more useful than
    demanding a repair. One missing or altered file is a torn state, and the
    report says which.
    """
    state_root = Path(state_root)
    marker = _read(marker_path(state_root))
    if marker is None:
        return {"state": "CLEAN", "unit": None, "missing": [], "altered": []}
    now = now if now is not None else marker.get("opened_at", 0)
    missing, altered = [], []
    for item in marker.get("files", []):
        target = state_root / item["path"]
        try:
            data = target.read_bytes()
        except OSError:
            missing.append(item["path"])
            continue
        if _digest(data) != item.get("sha256"):
            altered.append(item["path"])
    if missing or altered:
        verdict = "TORN"
    else:
        verdict = "COMPLETE_UNCLOSED"
    return {
        "state": verdict,
        "unit": marker.get("unit"),
        "session": marker.get("session"),
        "files": [item["path"] for item in marker.get("files", [])],
        "missing": sorted(missing),
        "altered": sorted(altered),
        "abandoned": bool(now - marker.get("opened_at", 0) > ABANDONED_AFTER_SECONDS),
    }
