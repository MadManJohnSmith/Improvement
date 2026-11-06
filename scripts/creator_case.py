"""Constructor del caso de evaluación desde un run terminado del Creator.

Dado el directorio de un run (run.json, generation-request.json,
creator-session.json, generated/) y el journal de la sesión de DSH, deriva
los hechos registrados sin transcripción manual: el modelo sale del
encabezado de la petición del journal, el uso, los pasos, el motivo de
parada y el cursor del estado persistido de la sesión, el manifiesto y la
prevalidación se re-ejecutan sobre las salidas del run, y los conteos se
recalculan del journal con las mismas reglas del evaluador. Escribe
facts.json, criteria.json y el journal en el directorio de caso y deja el
veredicto a creator_eval.evaluate_case, cuyo núcleo no cambia.

El journal que no se puede descubrir es un fallo cerrado: no se escribe
caso. La inconsistencia entre los hechos derivados y el journal la detecta
después grade() como ABSTAIN, nunca como PASS.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK / "scripts"))

import creator_eval
from creator_client import DSH_HOME_CANDIDATES
from host_validator import validate_package

# El mismo home que usaría un proceso DSH recién lanzado: el entorno manda y
# los candidatos estándar cubren instalaciones sin variable.
SESSION_USAGE_FIELDS = ("usage_input_tokens", "usage_output_tokens",
                        "usage_tokens", "usage_cache_read_tokens",
                        "usage_steps")


def resolve_dsh_home(explicit=None):
    """Resolve the DSH home: flag, then env, then the standard candidates."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get("DSH_HOME")
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()
    for candidate in DSH_HOME_CANDIDATES:
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path.resolve()
    return None


def _require_session_id(value):
    """A plain directory name: the scan joins it under sessions/<slug>/."""
    if (not isinstance(value, str) or not value.strip() or
            value in (".", "..") or "/" in value or "\\" in value):
        raise ValueError(
            "session_id ausente o inválido en creator-session.json")
    return value


def discover_journal(dsh_home, session_id):
    """Find one journal for the session without reconstructing the slug.

    The attached cwd changed across harnesses, so the slug is not derived:
    every ``sessions/*/<sessionId>/`` directory is scanned for the journal
    names the evaluator accepts. Zero matches is a closed failure; more than
    one is ambiguity, not a guess.
    """
    sessions = Path(dsh_home) / "sessions"
    if not sessions.is_dir():
        raise ValueError(f"El home de DSH no tiene sessions/: {dsh_home}")
    matches = []
    for slug in sorted(sessions.iterdir()):
        session_dir = slug / session_id
        if not session_dir.is_dir():
            continue
        for name in creator_eval.JOURNAL_FILES:
            candidate = session_dir / name
            if candidate.is_file():
                matches.append(candidate)
    if not matches:
        raise ValueError(
            f"Journal no descubierto para {session_id} bajo "
            f"{sessions}/*/<sessionId>/")
    if len(matches) > 1:
        listed = ", ".join(str(path) for path in sorted(matches))
        raise ValueError(f"Journales ambiguos para {session_id}: {listed}")
    return matches[0]


def _model_from_events(events):
    """Provider/model joined from the first request/header of the journal."""
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "request/header":
            continue
        data = event.get("data")
        header = data.get("header") if isinstance(data, dict) else None
        config = header.get("config") if isinstance(header, dict) else None
        if not isinstance(config, dict):
            return None
        provider = config.get("provider")
        model = config.get("model")
        if isinstance(provider, str) and provider and \
                isinstance(model, str) and model:
            return f"{provider}/{model}"
        if isinstance(model, str) and model:
            return model
        return None
    return None


def _turns_started(events):
    return sum(1 for event in events
               if isinstance(event, dict) and event.get("type") == "turn/start")


def _prevalidation_passed(run_dir, validate):
    """Re-run the Host prevalidation on the generated package.

    The run documents do not record the verdict, so it is observed again:
    any failure to validate is ``False``, never an exception to the caller.
    """
    try:
        report = validate(run_dir / "generated", run_dir=run_dir)
    except Exception:
        return False
    return bool(getattr(report, "passed", False))


def derive_facts(run_dir, events, session, *, validate=None):
    """Derive the recorded facts of a finished run from its own evidence.

    Absent sources are omitted, never invented: an incomplete run leaves the
    matching gap for grade() to abstain on. ``journal_event_count`` and the
    frame accounting reuse the evaluator's rules so facts and journal are
    held to one standard.
    """
    run_dir = Path(run_dir)
    run_doc, _ = creator_eval._read_json(run_dir / "run.json")
    creator_eval._require_dict(run_doc, "run.json")
    request, _ = creator_eval._read_json(run_dir / "generation-request.json")
    creator_eval._require_dict(request, "generation-request.json")
    creator_eval._require_dict(session, "creator-session.json")

    facts = {}
    generation_id = run_doc.get("generation_id")
    if isinstance(generation_id, str) and generation_id:
        facts["generation_id"] = generation_id
    project = run_doc.get("project")
    if isinstance(project, dict):
        named = {key: project[key] for key in ("name", "root_identity")
                 if isinstance(project.get(key), str) and project[key]}
        if named:
            facts["project"] = named
    revision = run_doc.get("framework_revision")
    if isinstance(revision, str) and revision:
        facts["framework_revision"] = revision
    budget = run_doc.get("budget")
    if isinstance(budget, dict):
        facts["budget"] = dict(budget)
    prompt_version = request.get("prompt_version")
    if isinstance(prompt_version, str) and prompt_version:
        facts["prompt_version"] = prompt_version

    for name in SESSION_USAGE_FIELDS:
        if creator_eval._is_int(session.get(name)):
            facts[name] = session[name]
    reason = session.get("reason")
    if isinstance(reason, str) and reason:
        facts["stop_reason"] = reason
    if isinstance(session.get("terminal"), bool):
        facts["terminal_turn"] = session["terminal"]
    if creator_eval._is_int(session.get("cursor")):
        facts["journal_last_seq"] = session["cursor"]

    model = _model_from_events(events)
    if model:
        facts["model"] = model
    facts["turns_started"] = _turns_started(events)
    facts["journal_event_count"] = creator_eval._frame_count(events)
    facts["manifest_present"] = (
        run_dir / "generated" / "generation-manifest.json").is_file()
    facts["prevalidation_passed"] = _prevalidation_passed(
        run_dir, validate if validate is not None else validate_package)
    return facts


def _copy_journal(source, case_dir):
    """Copy the discovered journal into the case under its original name."""
    foreign = [name for name in creator_eval.JOURNAL_FILES
               if name != source.name and (case_dir / name).exists()]
    if foreign:
        raise ValueError("El caso ya contiene otro journal: %s; deja uno"
                         % ", ".join(foreign))
    target = case_dir / source.name
    handle = tempfile.NamedTemporaryFile(
        "wb", dir=str(case_dir), prefix=target.name + ".", suffix=".tmp",
        delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def build_case(run_dir, case_dir, criteria, *, dsh_home=None, validate=None):
    """Derive the facts of one finished run and assemble its case directory.

    Writes facts.json, criteria.json and the discovered journal, in that
    order, after every closed failure has been ruled out: a run or journal
    that cannot be derived leaves the case directory untouched. Returns the
    derived facts.
    """
    criteria = creator_eval._require_criteria(criteria)
    run_dir = Path(run_dir)
    case_dir = Path(case_dir)
    session, _ = creator_eval._read_json(run_dir / "creator-session.json")
    creator_eval._require_dict(session, "creator-session.json")
    session_id = _require_session_id(session.get("session_id"))
    home = resolve_dsh_home(dsh_home)
    if home is None:
        raise ValueError(
            "Home de DSH no disponible: pasa --dsh-home o define DSH_HOME")
    journal = discover_journal(home, session_id)
    events, _ = creator_eval._read_events(journal, journal.name)
    facts = derive_facts(run_dir, events, session, validate=validate)
    case_dir.mkdir(parents=True, exist_ok=True)
    creator_eval._write_report(
        case_dir / "facts.json",
        json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    creator_eval._write_report(
        case_dir / "criteria.json",
        json.dumps(criteria, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n")
    _copy_journal(journal, case_dir)
    return facts
