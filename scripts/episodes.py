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

And one rule decides what may be trusted:

* **The ledger is the record; the index is its cache.** `record` appends in
  place with `O_APPEND` and fsyncs, so the ledger survives what the index does
  not: the index is a file replaced atomically next to it, and a state directory
  can lose one without the other. Every read therefore derives the index from
  the ledger and rewrites it only when they disagree, which is what stops a
  lost cache from turning a proven repair into a repeat.
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


def _ledger_signatures(workspace):
    """Signatures in the order the ledger holds them, capped per signature.

    Reads the ledger rather than the index because the ledger is what a crash
    cannot take: `record` appends to it in place with `O_APPEND`, while the
    index is replaced atomically and can therefore be absent while the ledger
    still holds everything that was ever proven.
    """
    grouped = {}
    for episode in read_episodes(workspace):
        signature = episode.get("signature")
        if not isinstance(signature, str) or not signature:
            continue
        grouped.setdefault(signature, []).append(episode)
        del grouped[signature][:-MAX_PER_SIGNATURE]
    return grouped


def _entry(episode):
    """The part of an episode the index keeps: enough to recall without the log."""
    if (not isinstance(episode, dict) or not isinstance(episode.get("unit"), str)
            or not isinstance(episode.get("verdict"), str)
            or not isinstance(episode.get("evidence"), str)):
        return None
    return {"unit": episode["unit"], "verdict": episode["verdict"],
            "evidence": episode["evidence"], "repair": episode.get("repair")}


def _write_index(workspace, signatures):
    index = {"version": VERSION, "signatures": dict(sorted(signatures.items()))}
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
    return index


def read_index(workspace):
    """The index, rebuilt from the ledger whenever the two disagree.

    The index is a cache over the ledger, and it is rebuilt rather than trusted:
    the state directory that holds it can lose it without the ledger losing
    anything, and an index that stops matching the ledger is that -- not a
    defect to report and not an empty memory to answer with. Before this, a
    lost index made `recall` answer [] for a defect whose verified repair was
    still on disk, so the auditor wrote the finding again and the record grew
    the duplicate the memory exists to stop.

    Only what cannot be explained as a lost cache is still refused: an index
    that exists and cannot be parsed is left alone and raised, because
    rewriting it would then overwrite content nobody can read back, and the
    reader in `dsh-plugins/workflow-write.mjs` refuses the same file on the
    same ground -- guessing whether a defect is new is the failure.
    """
    existing = _read_json(index_path(workspace),
                          {"version": VERSION, "signatures": {}})
    if not isinstance(existing.get("signatures"), dict):
        raise ValueError("índice de episodios con forma inesperada")
    rebuilt = {
        signature: [entry for entry in
                    (filter(None, (_entry(e) for e in episodes)))]
        for signature, episodes in _ledger_signatures(workspace).items()
    }
    if existing["signatures"] != rebuilt:
        return _write_index(workspace, rebuilt)
    return existing


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
    """Write the index the ledger now describes, in one place.

    `record` appends first and then calls this, so deriving the index from the
    ledger -- rather than merging the new entry into whatever the index already
    said -- keeps one writer: an index outlives the append that produced it, and
    a merge can keep an entry the ledger's own cap has already dropped.
    """
    del episode  # the ledger is the record; the caller has already appended.
    read_index(workspace)


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


def citation_valid(workspace, prior_episode, fingerprint=None):
    """Is a finding's 'already closed before' citation still true?

    A finding carries `evidence.prior_episode`, which is the episode the tool
    echoed from the index when the finding was written
    (`dsh-plugins/workflow-write.mjs:630-652`). The citation names a unit and
    echoes that unit's evidence and repair, and the signature it was recalled by
    is the finding's `evidence.fingerprint` -- the tool computes that itself and
    refuses to let a mode write it.

    So the claim has two halves, and the memory can contradict either:

    * **the cited unit closed nothing** -- the ledger no longer holds any episode
      by that unit, so the citation points at a deletion. That is the drift
      `state_reconcile.memory` reports as `unknown_claimed_units`.
    * **the cited unit never closed this defect** -- the unit has episodes, but
      none under the signature the finding was filed against, so the repair
      being cited does not close the defect in the finding. This is the half
      that the unit-only check cannot see, and it is the one that matters: the
      finding is right that a repair exists and wrong that it closes *this*
      defect, so the defect gets filed again every session and the record grows
      exactly the duplicate the memory exists to stop.

    When the caller does not know the signature, only the first half is
    answered, and the answer is then "the unit closed something", which is the
    weaker claim rather than a false one.
    """
    if not isinstance(prior_episode, dict):
        return False
    unit = prior_episode.get("unit")
    if not isinstance(unit, str) or not unit:
        return False
    signatures = read_index(workspace)["signatures"]
    if isinstance(fingerprint, str) and fingerprint:
        return any(entry.get("unit") == unit
                   for entry in signatures.get(fingerprint, [])
                   if isinstance(entry, dict))
    return any(entry.get("unit") == unit
               for group in signatures.values()
               for entry in group
               if isinstance(entry, dict))


def stats(workspace):
    """How much the framework remembers, counted from the ledger.

    The count is what an operator reads in the reconciliation report, so it has
    to be the ledger's count: the index is capped per signature
    (`MAX_PER_SIGNATURE`) and is derived, so counting it understated a project
    whose ledger held more repairs than the cache kept.
    """
    index = read_index(workspace)
    ledger = ledger_path(workspace)
    return {
        "signatures": len(index["signatures"]),
        "episodes": len(read_episodes(workspace)),
        "ledger_bytes": ledger.stat().st_size if ledger.exists() else 0,
    }
