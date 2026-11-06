"""Evaluador de una corrida registrada del Creator: veredicto cerrado.

No ejecuta sesiones ni contacta proveedor: consume los hechos de la corrida y
el journal de la sesión de DSH, y decide si el paquete se completó y si el
patrón de lectura respetó el caso pre-registrado. La evidencia incompleta se
declara ABSTAIN, nunca PASS.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

VERDICTS = ("PASS", "FAIL_MECHANISM", "FAIL_COMPLETION", "ABSTAIN")

# Tipos observados en un journal real. Un tipo nuevo se reporta como
# desconocido y no se descarta en silencio; no invalida la corrida.
KNOWN_EVENT_TYPES = frozenset({
    "session", "session/title", "permission/preset", "sandbox/mode",
    "approval/policy", "agent/inbox/spliced", "turn/start", "step/start",
    "step/end", "assistant/message", "tool/call", "tool/result",
    "user/message", "system/message", "request/header", "request/context",
    "turn/end", "error",
})

REQUIRED_CRITERIA = ("forbidden_schema_reads", "require_manifest",
                     "require_prevalidation")


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} inválido")


def _require_criteria(criteria):
    _require_dict(criteria, "Criterios")
    missing = [key for key in REQUIRED_CRITERIA if key not in criteria]
    if missing:
        raise ValueError(f"Criterios incompletos: {missing}")
    forbidden = criteria["forbidden_schema_reads"]
    if (not isinstance(forbidden, list) or
            not all(isinstance(name, str) and name for name in forbidden)):
        raise ValueError("forbidden_schema_reads inválido")
    for key in ("require_manifest", "require_prevalidation"):
        if not isinstance(criteria[key], bool):
            raise ValueError(f"{key} inválido")
    return criteria


def _mention(text, name):
    """True when ``name`` appears as a path, not as part of another name."""
    if not isinstance(text, str):
        return False
    pattern = r"(?<![\w.-])" + re.escape(name) + r"(?![\w.-])"
    return re.search(pattern, text) is not None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _arguments(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _calls(events):
    """Return tool calls, malformed frames and unknown event types."""
    calls, malformed, unknown = [], 0, set()
    for event in events:
        if not isinstance(event, dict):
            malformed += 1
            continue
        kind = event.get("type")
        if kind == "tool/call":
            data = event.get("data")
            name = data.get("name") if isinstance(data, dict) else None
            if not isinstance(name, str) or not name:
                malformed += 1
                continue
            calls.append((name, _arguments(data.get("arguments"))))
        elif not isinstance(kind, str) or kind not in KNOWN_EVENT_TYPES:
            unknown.add(kind if isinstance(kind, str) else "<sin tipo>")
    return calls, malformed, sorted(unknown)


def _frame_count(events):
    """Frames exclude the session header, which is metadata and not a turn."""
    return sum(1 for event in events
               if not (isinstance(event, dict) and event.get("type") == "session"))


def _last_seq(events):
    seqs = [event["seq"] for event in events
            if isinstance(event, dict) and isinstance(event.get("seq"), int)]
    return max(seqs) if seqs else 0


def _counts(calls, forbidden):
    tool_calls, schema_reads, reader_calls = {}, {}, 0
    for name, arguments in calls:
        tool_calls[name] = tool_calls.get(name, 0) + 1
        texts = list(_strings(arguments))
        if any(_mention(text, "read_view.py") for text in texts):
            # A bounded view is the sanctioned path, not a full read.
            reader_calls += 1
            continue
        for schema in forbidden:
            if any(_mention(text, schema) for text in texts):
                schema_reads[schema] = schema_reads.get(schema, 0) + 1
    return (dict(sorted(tool_calls.items())),
            dict(sorted(schema_reads.items())), reader_calls)


def _identity(facts):
    project = facts.get("project")
    return project.get("root_identity") if isinstance(project, dict) else None


def _descriptive(facts):
    tokens = facts.get("usage_tokens")
    cache = facts.get("usage_cache_read_tokens")
    share = None
    if isinstance(tokens, int) and tokens > 0 and isinstance(cache, int):
        share = round(cache / tokens, 4)
    return {
        "usage_tokens": tokens,
        "cache_read_tokens": cache,
        "cache_share": share,
        "steps": facts.get("usage_steps"),
        "elapsed_seconds": facts.get("elapsed_seconds"),
    }


def grade(facts, events, criteria):
    """Return one closed verdict for a recorded run.

    The rules are pre-registered in the case: an incomplete observation
    abstains, a missing package is a completion failure, a complete package
    with a forbidden schema read is a mechanism failure, and only a complete
    package with no forbidden read passes.
    """
    _require_dict(facts, "Hechos")
    criteria = _require_criteria(criteria)
    if not isinstance(events, list):
        raise ValueError("Journal inválido")

    calls, malformed, unknown = _calls(events)
    tool_calls, schema_reads, reader_calls = _counts(
        calls, criteria["forbidden_schema_reads"])
    identity = _identity(facts)

    integrity = None
    completion = None
    mechanism = None
    if not isinstance(facts.get("model"), str) or not facts["model"].strip():
        integrity = "model ausente: la corrida no se puede calificar"
    elif not isinstance(identity, str) or not identity.strip():
        integrity = "root_identity ausente: el producto no está identificado"
    elif malformed:
        integrity = f"journal malformado: {malformed} frame(s) sin forma"
    elif not calls:
        integrity = "journal sin llamadas de herramienta: no hay corrida que calificar"
    elif facts.get("journal_event_count") != _frame_count(events):
        integrity = ("event_count no coincide: hechos=%r journal=%d"
                     % (facts.get("journal_event_count"), _frame_count(events)))
    elif (isinstance(facts.get("journal_last_seq"), int) and
          facts["journal_last_seq"] != _last_seq(events)):
        integrity = ("last_seq no coincide: hechos=%r journal=%d"
                     % (facts.get("journal_last_seq"), _last_seq(events)))
    elif (criteria["require_manifest"] and
          not isinstance(facts.get("manifest_present"), bool)):
        integrity = "manifest_present ausente en los hechos"
    elif (criteria["require_prevalidation"] and
          not isinstance(facts.get("prevalidation_passed"), bool)):
        integrity = "prevalidation_passed ausente en los hechos"

    if integrity:
        verdict, reason = "ABSTAIN", integrity
    else:
        if criteria["require_manifest"] and not facts["manifest_present"]:
            completion = "generation-manifest.json ausente"
        elif (criteria["require_prevalidation"] and
              not facts["prevalidation_passed"]):
            completion = "prevalidación Host no superada"
        if completion:
            verdict, reason = "FAIL_COMPLETION", completion
        elif schema_reads:
            mechanism = "lectura completa de schema: " + ", ".join(schema_reads)
            verdict, reason = "FAIL_MECHANISM", mechanism
        else:
            mechanism = "sin lecturas completas de los schemas del caso"
            verdict, reason = "PASS", "criterios cumplidos"

    return {
        "verdict": verdict,
        "reason": reason,
        "case": criteria.get("id"),
        "evidence": [
            {"criterion": "integrity",
             "ok": integrity is None,
             "detail": integrity or "hechos y journal concuerdan"},
            {"criterion": "completion",
             "ok": None if integrity else completion is None,
             "detail": None if integrity else (completion or "paquete completo")},
            {"criterion": "mechanism",
             "ok": None if (integrity or completion) else not schema_reads,
              "detail": None if (integrity or completion) else mechanism},
        ],
        "counts": {
            "tool_calls": tool_calls,
            "schema_reads": schema_reads,
            "reader_calls": reader_calls,
        },
        "descriptive": _descriptive(facts),
        "unknown_types": unknown,
        "malformed_events": malformed,
        "seq_checked": isinstance(facts.get("journal_last_seq"), int),
    }


DECOMPRESSOR = "zstd"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"No se puede leer {path.name}: {error}") from error
    except ValueError as error:
        raise ValueError(f"JSON inválido en {path.name}: {error}") from error


def _journal_path(case):
    plain = case / "journal.jsonl"
    compressed = case / "journal.jsonl.zstd"
    if plain.exists() and compressed.exists():
        raise ValueError("journal.jsonl y journal.jsonl.zstd: deja uno")
    if plain.exists():
        return plain, "journal.jsonl"
    if compressed.exists():
        return compressed, "journal.jsonl.zstd"
    raise ValueError("Falta journal.jsonl o journal.jsonl.zstd en el caso")


def _read_events(path, source):
    if source.endswith(".zstd"):
        try:
            done = subprocess.run([DECOMPRESSOR, "-dc", "--", str(path)],
                                  capture_output=True, check=False)
        except FileNotFoundError as error:
            raise ValueError(f"Descompresor ausente: {DECOMPRESSOR}") from error
        if done.returncode != 0:
            detail = done.stderr.decode("utf-8", "replace").strip()
            raise ValueError(
                f"Journal comprimido ilegible: {detail or path.name}") from None
        try:
            text = done.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Journal no UTF-8: {path.name}") from error
    else:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"No se puede leer {path.name}: {error}") from error
    events = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as error:
            raise ValueError(
                f"JSON inválido en {path.name}:{number}: {error}") from error
    return events


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_digests(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "ilegible"
    if not isinstance(data, dict):
        return "ilegible"
    return data.get("digests", "ilegible")


def evaluate_case(case_dir, report_path, *, overwrite=False):
    """Grade one case directory and retain the report with input digests."""
    case = Path(case_dir)
    report = Path(report_path)
    if not case.is_dir():
        raise ValueError(f"Caso ausente o no regular: {case}")
    facts_path = case / "facts.json"
    criteria_path = case / "criteria.json"
    journal_path, journal_file = _journal_path(case)
    facts = _read_json(facts_path)
    criteria = _read_json(criteria_path)
    events = _read_events(journal_path, journal_file)
    digests = {"facts": _sha256(facts_path),
               "criteria": _sha256(criteria_path),
               "journal": _sha256(journal_path)}
    existing = _existing_digests(report)
    if existing is not None and existing != digests and not overwrite:
        raise ValueError(
            f"El informe {report.name} existe con otros digests; "
            "usa --overwrite para reemplazarlo")
    result = grade(facts, events, criteria)
    result["digests"] = digests
    result["journal_file"] = journal_file
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="creator_eval.py",
        description="Califica una corrida de Creator y retiene el informe con digests.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        evaluate_case(args.case, args.report, overwrite=args.overwrite)
    except (OSError, ValueError) as error:
        print(f"creator_eval: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
