"""Evaluador de una corrida registrada del Creator: veredicto cerrado.

No ejecuta sesiones ni contacta proveedor: consume los hechos de la corrida y
el journal de la sesión de DSH, y decide si el paquete se completó y si el
patrón de lectura respetó el caso pre-registrado. La evidencia incompleta se
declara ABSTAIN, nunca PASS. La única excepción deliberada es un
``journal_last_seq`` ausente: los hechos de un harness anterior no lo
registraban, y en ese caso el conteo de frames sigue atando el journal; un
valor presente que no coincide o no es entero sí abstiene.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

DECOMPRESSOR = "zstd"

# Tipos observados en un journal real. Un tipo nuevo se cuenta y se reporta;
# no invalida la corrida. Un frame sin tipo es distinto: es un journal roto.
KNOWN_EVENT_TYPES = frozenset({
    "session", "session/title", "permission/preset", "sandbox/mode",
    "approval/policy", "agent/inbox/spliced", "turn/start", "step/start",
    "step/end", "assistant/message", "tool/call", "tool/result",
    "user/message", "system/message", "request/header", "request/context",
    "turn/end", "error",
})

REQUIRED_CRITERIA = ("forbidden_schema_reads", "require_manifest",
                     "require_prevalidation")

JOURNAL_FILES = ("journal.jsonl", "journal.jsonl.zstd", "session.v4.jsonl.zstd")

_UNPARSEABLE = object()


def require_dict(value, label):
    """Require a JSON object, by name: the closed failure says which file."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} inválido")


def require_criteria(criteria):
    require_dict(criteria, "Criterios")
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


def is_int(value):
    """A boolean is not a count: ``True == 1`` must not satisfy a match."""
    return type(value) is int


def text_or_none(source, key):
    """A non-empty string field of ``source``, or None when it is absent.

    The single place of the "recorded text or omit" predicate: the facts
    derivation (creator_case) and the roster projection (creator_roster)
    both refuse to invent a value the case did not record, so an absent or
    empty source field is an omission, never an empty string.
    """
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, str) and value else None


def int_or_none(source, key):
    """An integer field of ``source``, or None: a boolean is not a count."""
    value = source.get(key) if isinstance(source, dict) else None
    return value if is_int(value) else None


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
            return _UNPARSEABLE
    return raw


def _bash_surfaces(command):
    """Return the tokens that could name a file, and the reader invocations.

    The reader's own ``--path`` is excluded only when the same invocation also
    asks for a range: an unbounded view is a full read and has to count.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    ranged = any(token in ("--start", "--end") or
                 token.startswith("--start=") or token.startswith("--end=")
                 for token in tokens)
    surfaces, readers = [], 0
    skip_next = False
    seen_reader = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token.endswith("read_view.py"):
            readers += 1
            seen_reader = True
            continue
        if seen_reader and ranged and token in ("--path", "-p"):
            skip_next = True
            continue
        if seen_reader and ranged and token.startswith("--path="):
            continue
        surfaces.append(token)
    return surfaces, readers


def _surfaces(name, arguments):
    """Only read-capable surfaces count; written content is not a read."""
    if not isinstance(arguments, dict):
        return [], 0
    if name == "bash":
        command = arguments.get("command")
        if isinstance(command, str):
            return _bash_surfaces(command)
        return [], 0
    if name == "read":
        # The read tool has used both `path` and `file_path`; its arguments
        # are the target, so every value is a read surface.
        return list(_strings(arguments)), 0
    return [], 0


def _calls(events):
    """Return tool calls, malformed frames and unknown event type counts."""
    calls, malformed, unknown = [], 0, {}
    for event in events:
        if not isinstance(event, dict):
            malformed += 1
            continue
        kind = event.get("type")
        if not isinstance(kind, str) or not kind:
            malformed += 1
            continue
        if kind == "tool/call":
            data = event.get("data")
            name = data.get("name") if isinstance(data, dict) else None
            if not isinstance(name, str) or not name:
                malformed += 1
                continue
            parsed = _arguments(data.get("arguments"))
            if parsed is _UNPARSEABLE:
                malformed += 1
                continue
            seq = event.get("seq")
            calls.append((name, parsed, seq if is_int(seq) else None))
        elif kind not in KNOWN_EVENT_TYPES:
            unknown[kind] = unknown.get(kind, 0) + 1
    return calls, malformed, dict(sorted(unknown.items()))


def frame_count(events):
    """Frames exclude the session header, which is metadata and not a turn."""
    return sum(1 for event in events
               if not (isinstance(event, dict) and event.get("type") == "session"))


def _last_seq(events):
    seqs = [event["seq"] for event in events
            if isinstance(event, dict) and is_int(event.get("seq"))]
    return max(seqs) if seqs else 0


def frame_span_seconds(events):
    """Elapsed seconds from the first to the last timestamped frame.

    The frames that carry a ``seq`` also carry ``time`` in epoch
    milliseconds; the session header carries neither. The span between the
    first and the last timestamped frame is the defensible duration of the
    run: persisted evidence read by the same rules as every other journal
    count, not wall-clock taken at derivation time. Rounded to hundredths of
    a second, like the case derived by hand that fixed the column. None when
    no frame carries a time (the duration is omitted, not zero) or when the
    span is negative: a clock skew is inconsistent evidence, not a duration.
    """
    times = [event["time"] for event in events
             if isinstance(event, dict) and is_int(event.get("seq"))
             and is_int(event.get("time"))]
    if not times:
        return None
    elapsed = (times[-1] - times[0]) / 1000
    return round(elapsed, 2) if elapsed >= 0 else None


def _counts(calls, forbidden):
    tool_calls, schema_reads, reader_calls = {}, {}, 0
    read_events = {}
    for name, arguments, seq in calls:
        tool_calls[name] = tool_calls.get(name, 0) + 1
        surfaces, readers = _surfaces(name, arguments)
        reader_calls += readers
        for schema in forbidden:
            if any(_mention(text, schema) for text in surfaces):
                schema_reads[schema] = schema_reads.get(schema, 0) + 1
                if seq is not None:
                    read_events.setdefault(schema, []).append(seq)
    return (dict(sorted(tool_calls.items())),
            dict(sorted(schema_reads.items())), reader_calls,
            {key: sorted(value) for key, value in sorted(read_events.items())})


def _identity(facts):
    project = facts.get("project")
    return project.get("root_identity") if isinstance(project, dict) else None


def _descriptive(facts):
    tokens = facts.get("usage_tokens")
    cache = facts.get("usage_cache_read_tokens")
    share = None
    if is_int(tokens) and tokens > 0 and is_int(cache):
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
    require_dict(facts, "Hechos")
    criteria = require_criteria(criteria)
    if not isinstance(events, list):
        raise ValueError("Journal inválido")

    calls, malformed, unknown = _calls(events)
    tool_calls, schema_reads, reader_calls, read_events = _counts(
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
    elif not is_int(facts.get("journal_event_count")):
        integrity = "event_count ausente o inválido en los hechos"
    elif facts["journal_event_count"] != frame_count(events):
        integrity = ("event_count no coincide: hechos=%r journal=%d"
                     % (facts["journal_event_count"], frame_count(events)))
    elif ("journal_last_seq" in facts and
          not is_int(facts["journal_last_seq"])):
        integrity = "last_seq inválido en los hechos"
    elif ("journal_last_seq" in facts and
          facts["journal_last_seq"] != _last_seq(events)):
        integrity = ("last_seq no coincide: hechos=%r journal=%d"
                     % (facts["journal_last_seq"], _last_seq(events)))
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
            "schema_read_events": read_events,
            "reader_calls": reader_calls,
        },
        "descriptive": _descriptive(facts),
        "unknown_types": unknown,
        "malformed_events": malformed,
        "seq_checked": "journal_last_seq" in facts,
    }


def read_json(path):
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"No se puede leer {path.name}: {error}") from error
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"{path.name} no es UTF-8: {error}") from error
    except ValueError as error:
        raise ValueError(f"JSON inválido en {path.name}: {error}") from error
    return data, hashlib.sha256(raw).hexdigest()


def _journal_path(case):
    present = [name for name in JOURNAL_FILES if (case / name).exists()]
    if len(present) > 1:
        raise ValueError("Journales ambiguos: %s; deja uno" % ", ".join(present))
    if not present:
        raise ValueError("Falta journal.jsonl, journal.jsonl.zstd o "
                         "session.v4.jsonl.zstd en el caso")
    return case / present[0], present[0]


def read_events(path, source):
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"No se puede leer {path.name}: {error}") from error
    if source.endswith(".zstd"):
        try:
            done = subprocess.run([DECOMPRESSOR, "-dc"], input=raw,
                                  capture_output=True, check=False)
        except FileNotFoundError as error:
            raise ValueError(f"Descompresor ausente: {DECOMPRESSOR}") from error
        if done.returncode != 0:
            detail = done.stderr.decode("utf-8", "replace").strip()
            raise ValueError(
                f"Journal comprimido ilegible: {detail or path.name}") from None
        payload = done.stdout
    else:
        payload = raw
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Journal no UTF-8: {path.name}") from error
    events = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as error:
            raise ValueError(
                f"JSON inválido en {path.name}:{number}: {error}") from error
    return events, hashlib.sha256(raw).hexdigest()


def _existing_digests(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "ilegible"
    if not isinstance(data, dict):
        return "ilegible"
    digests = data.get("digests")
    if not isinstance(digests, dict):
        return "ilegible"
    return digests


def write_report(path, payload):
    handle = tempfile.NamedTemporaryFile(
        "w", dir=str(path.parent), prefix=path.name + ".", suffix=".tmp",
        delete=False, encoding="utf-8")
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def evaluate_case(case_dir, report_path, *, overwrite=False):
    """Grade one case directory and retain the report with input digests."""
    case = Path(case_dir)
    report = Path(report_path)
    if not case.is_dir():
        raise ValueError(f"Caso ausente o no regular: {case}")
    facts_path = case / "facts.json"
    criteria_path = case / "criteria.json"
    journal_path, journal_file = _journal_path(case)
    facts, facts_digest = read_json(facts_path)
    criteria, criteria_digest = read_json(criteria_path)
    events, journal_digest = read_events(journal_path, journal_file)
    digests = {"facts": facts_digest, "criteria": criteria_digest,
               "journal": journal_digest}
    existing = _existing_digests(report)
    if existing == "ilegible" and not overwrite:
        raise ValueError(f"El informe {report.name} es ilegible; usa --overwrite")
    if (existing not in (None, "ilegible") and existing != digests and
            not overwrite):
        raise ValueError(
            f"El informe {report.name} existe con otros digests; "
            "usa --overwrite para reemplazarlo")
    result = grade(facts, events, criteria)
    result["digests"] = digests
    result["journal_file"] = journal_file
    write_report(report, json.dumps(
        result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return result


INDEX_REQUIRED = ("id", "expected_verdict", "prompt_version", "run_id",
                  "journal", "journal_sha256")


def validate_index(index_path):
    """Valida la estructura del índice del corpus, sin leer evidencia.

    Fail-closed: entradas sin claves usables, digests que no son hex64, ids
    duplicados o un corpus vacío son error, no advertencia. La existencia de
    casos y journals se comprueba al puntuar, donde el fallo se atribuye al
    caso y no al índice.
    """
    data, _ = read_json(Path(index_path))
    require_dict(data, "índice del corpus")
    entries = data.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("el índice del corpus no declara casos: "
                         "'cases' ausente o vacío")
    seen = set()
    for entry in entries:
        require_dict(entry, "entrada del índice")
        for key in INDEX_REQUIRED:
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"entrada sin '{key}' usable: "
                                 f"{entry.get('id', '?')}")
        digest = entry["journal_sha256"]
        if len(digest) != 64 or set(digest.lower()) - set("0123456789abcdef"):
            raise ValueError(f"journal_sha256 no es hex64: {entry['id']}")
        if entry["id"] in seen:
            raise ValueError(f"id duplicado en el índice: {entry['id']}")
        seen.add(entry["id"])
    return entries


def score_corpus(index_path, *, evidence_root, prompt_path=None):
    """Puntúa el corpus: lectura pura, determinista y fail-closed.

    El journal de cada caso es evidencia externa referida por el índice; su
    digest se verifica antes de calificar y un desajuste es error del caso,
    nunca un salto silencioso. Con errores de integridad el puntaje omite
    correct/abstain/mismatches: un corpus herido no se publica como sano.
    """
    index = Path(index_path)
    entries = validate_index(index)
    evidence = Path(evidence_root)
    details = []
    errors = []
    versions = set()
    for entry in sorted(entries, key=lambda item: item["id"]):
        cid = entry["id"]
        try:
            case_dir = index.parent / cid
            if not case_dir.is_dir():
                raise ValueError(f"caso ausente en el índice: {cid}")
            facts, _ = read_json(case_dir / "facts.json")
            criteria, _ = read_json(case_dir / "criteria.json")
            journal = evidence / entry["journal"]
            events, journal_digest = read_events(journal, journal.name)
            if journal_digest != entry["journal_sha256"]:
                raise ValueError("el digest del journal no coincide con el "
                                 "índice")
            verdict = grade(facts, events, criteria)["verdict"]
        except (OSError, ValueError) as error:
            errors.append({"id": cid, "reason": str(error)})
            continue
        versions.add(entry["prompt_version"])
        details.append({"id": cid, "expected": entry["expected_verdict"],
                        "actual": verdict,
                        "ok": verdict == entry["expected_verdict"]})
    score = {"cases": len(entries), "prompt_versions": sorted(versions)}
    if prompt_path is not None:
        score["prompt_bytes"] = Path(prompt_path).stat().st_size
    if errors:
        score["errors"] = errors
        return score
    score["errors"] = []
    score["correct"] = sum(1 for item in details if item["ok"])
    score["abstain"] = sum(1 for item in details if item["actual"] == "ABSTAIN")
    score["mismatches"] = [item["id"] for item in details if not item["ok"]]
    score["details"] = details
    return score


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="creator_eval.py",
        description="Califica una corrida de Creator y retiene el informe con digests.")
    parser.add_argument("--case",
                        help="Caso a calificar, o caso a construir con --from-run")
    parser.add_argument("--report",
                        help="Informe a retener; por defecto <case>/report.json "
                             "en modo --from-run")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--from-run", metavar="RUN_DIR", default=None,
                        help="Run terminado del Creator: deriva los hechos, "
                             "escribe el caso y lo califica")
    parser.add_argument("--criteria",
                        help="Criterios pre-registrados del caso "
                             "(obligatorio con --from-run)")
    parser.add_argument("--dsh-home",
                        help="Home de DSH donde descubrir el journal "
                             "(por defecto DSH_HOME o los candidatos estándar)")
    parser.add_argument("--project-root", metavar="PRODUCT_DIR", default=None,
                        help="Raíz del producto del run: sin ella los hechos "
                             "no llevan product_tree_digest y el campo se omite")
    parser.add_argument("--corpus", metavar="INDEX", default=None,
                        help="Índice del corpus (eval/cases/index.json): "
                             "puntúa todos los casos, sin escribir nada")
    parser.add_argument("--evidence", metavar="DIR", default=None,
                        help="Raíz de evidencia externa con los journals "
                             "(obligatorio con --corpus)")
    parser.add_argument("--prompt-file", metavar="PROMPT", default=None,
                        help="Fichero de prompt versionado: sin él el "
                             "puntaje omite prompt_bytes, nunca lo inventa")
    args = parser.parse_args(argv)
    try:
        if args.corpus and (args.case or args.from_run):
            raise ValueError("--corpus no se combina con --case ni --from-run")
        if not args.corpus and not args.case:
            raise ValueError("elige un modo: --case (opcionalmente con "
                             "--from-run) o --corpus")
        if args.corpus:
            if not args.evidence:
                raise ValueError("--evidence es obligatorio con --corpus")
            score = score_corpus(
                Path(args.corpus), evidence_root=Path(args.evidence),
                prompt_path=Path(args.prompt_file) if args.prompt_file else None)
            print(json.dumps(score, ensure_ascii=False, indent=2,
                             sort_keys=True))
            return 1 if score["errors"] else 0
        if args.from_run:
            if not args.criteria:
                raise ValueError("--criteria es obligatorio con --from-run")
            # Importe perezoso: la derivación arrastra el validador del Host
            # y el cliente Creator, que el modo de calificación pura no usa.
            import creator_case
            criteria, _ = read_json(Path(args.criteria))
            case_dir = Path(args.case)
            creator_case.build_case(args.from_run, case_dir, criteria,
                                    dsh_home=args.dsh_home,
                                    project_root=args.project_root)
            report = Path(args.report) if args.report else case_dir / "report.json"
            evaluate_case(case_dir, report, overwrite=args.overwrite)
        else:
            if not args.report:
                raise ValueError("--report es obligatorio")
            evaluate_case(args.case, args.report, overwrite=args.overwrite)
    except (OSError, ValueError) as error:
        print(f"creator_eval: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
