"""The reflection half of the RSI: what was refused, why, and by how much.

A gate that only says no is half a loop. The candidate is rejected, the reason
is printed, and the next editor starts from nothing: the same edit, or a
nearby one, gets proposed again and refused again for a reason already given.
That is the repetition failure this framework already paid for once in the
defect memory (E2), and paying it twice in the improvement loop would be the
same mistake in the place where it costs the most.

So a refusal is kept. The buffer records, per refused candidate, what it was,
what the gate said about it, and what the held-out score was before and after —
the three things a second attempt needs in order to be different rather than
merely new. Accepted candidates are not recorded: there is nothing to reflect
on, and a buffer that also collects successes becomes a changelog.

Three rules decide the shape:

* **The entry is bound to the corpus it was judged against.** A refusal earned
  on one corpus says nothing about another, and replaying it as if it did would
  be the one way this buffer could make the gate *less* honest than having no
  buffer. Entries from another corpus are refused, not filtered away.
* **Append in place.** A temp file plus `os.replace` would drop every earlier
  refusal, which is the opposite of what a memory is for.
* **Re-submitting a refused candidate is refused without running the gate.**
  The candidate digest is already in the buffer and the corpus has not moved,
  so the answer cannot have changed. Scoring it again would spend a full agent
  run to learn something already recorded.
"""

import json
import os
from pathlib import Path

VERSION = 1
MAX_ENTRIES = 256
MAX_REASONS = 8
MAX_REASON_BYTES = 256
MAX_LEDGER_BYTES = 4 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")


class ReflectionError(ValueError):
    pass


def _digest(value, label):
    if not isinstance(value, str) or len(value) != 64 or set(value) > _HEX:
        raise ReflectionError(f"{label} debe ser un sha256 hexadecimal")
    return value


def _reasons(reasons):
    if not isinstance(reasons, (list, tuple)):
        raise ReflectionError("reasons debe ser una lista de cadenas")
    kept = []
    for reason in reasons[:MAX_REASONS]:
        if not isinstance(reason, str) or not reason.strip():
            raise ReflectionError("cada reason debe ser texto no vacío")
        if len(reason.encode("utf-8")) > MAX_REASON_BYTES:
            raise ReflectionError(f"reason excede {MAX_REASON_BYTES} bytes")
        kept.append(reason)
    return kept


def read(buffer_path):
    """Every refusal still in the buffer, skipping a torn trailing line.

    A crash can leave the last append half-written, exactly as it can in the
    episodic ledger. A partial line is a crash, not corruption; anything
    malformed before it is corruption and is refused, because a silently
    shortened memory would forget a refusal the gate once gave.
    """
    path = Path(buffer_path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    lines = text.splitlines()
    entries = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError as error:
            if index == len(lines) - 1:
                continue
            raise ReflectionError(f"el búfer de reflexión tiene una línea inválida: {error}") from error
        if not isinstance(value, dict) or value.get("version") != VERSION:
            raise ReflectionError("el búfer de reflexión tiene una versión desconocida")
        entries.append(value)
    return entries


def record(buffer_path, *, corpus_digest, candidate_digest, action, reasons,
           baseline=None, candidate=None):
    """Keep one refusal. Accepting a candidate is not an entry.

    `baseline` and `candidate` are the held-out accuracies the gate compared.
    They are stored because "it got worse" is actionable and "0.512 vs 0.489"
    is what makes the next attempt different: without the numbers, the buffer
    only says the edit was refused, and the natural next move is to guess again.
    """
    if action not in ("reject", "abstain"):
        raise ReflectionError(
            f"solo se recuerdan rechazos y abstenciones, no {action!r}: "
            "un acierto no tiene nada que reflexionar")
    entry = {
        "version": VERSION,
        "corpus_digest": _digest(corpus_digest, "corpus_digest"),
        "candidate_digest": _digest(candidate_digest, "candidate_digest"),
        "action": action,
        "reasons": _reasons(reasons),
    }
    for name, value in (("baseline_validation", baseline),
                        ("candidate_validation", candidate)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReflectionError(f"{name} debe ser un número o nulo")
        entry[name] = float(value)
    _append(buffer_path, entry)
    return entry


def _append(buffer_path, entry):
    path = Path(buffer_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ReflectionError(f"el búfer de reflexión no puede ser un enlace: {path}")
    if path.exists() and path.stat().st_size > MAX_LEDGER_BYTES:
        raise ReflectionError("el búfer de reflexión supera el tope de disco")
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(handle, (json.dumps(entry, ensure_ascii=False, sort_keys=True)
                          + "\n").encode("utf-8"))
        os.fsync(handle)
    finally:
        os.close(handle)
    _trim(path)


def _trim(path):
    """Oldest refusals fall off, and the drop is reported, never silent."""
    entries = read(path)
    if len(entries) <= MAX_ENTRIES:
        return
    kept = entries[-MAX_ENTRIES:]
    temporary = path.with_name(f".{path.name}.trim")
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            for entry in kept:
                stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prior_refusal(buffer_path, corpus_digest, candidate_digest):
    """The refusal this exact candidate already earned on this exact corpus.

    `None` when there is none, which is the normal case and the only case a
    first attempt should ever hit.
    """
    for entry in read(buffer_path):
        if (entry.get("corpus_digest") == corpus_digest
                and entry.get("candidate_digest") == candidate_digest):
            return entry
    return None


def brief(buffer_path, corpus_digest=None, limit=10):
    """What the next attempt should read before making one.

    Newest first, and only for the given corpus when one is named: a refusal
    from another corpus describes different scenarios and would be advice about
    the wrong question.
    """
    entries = read(buffer_path)
    if corpus_digest is not None:
        _digest(corpus_digest, "corpus_digest")
        entries = [entry for entry in entries if entry.get("corpus_digest") == corpus_digest]
    entries = entries[-limit:][::-1] if limit else entries[::-1]
    lines = []
    for entry in entries:
        before = entry.get("baseline_validation")
        after = entry.get("candidate_validation")
        score = "sin puntuación comparable"
        if before is not None and after is not None:
            score = f"holdout {before:.3f} -> {after:.3f}"
        lines.append({
            "candidate_digest": entry["candidate_digest"],
            "action": entry["action"],
            "score": score,
            "reasons": entry.get("reasons", []),
        })
    return {"entries": lines, "total_refusals": len(read(buffer_path))}
