"""Constructor del caso de evaluación desde un run terminado del Creator.

Dado el directorio de un run (run.json, generation-request.json,
creator-session.json, generated/) y el journal de la sesión de DSH, deriva
los hechos registrados sin transcripción manual: el modelo sale del
encabezado de la petición del journal, el uso, los pasos, el motivo de
parada y el cursor del estado persistido de la sesión, la duración del
intervalo entre el primer y el último frame con ``time`` del journal, el
manifiesto y la prevalidación se re-ejecutan sobre las salidas del run, el
digest de árbol del producto se calcula con la convención del framework
cuando el constructor recibe su raíz, y los conteos se recalculan del
journal con las mismas reglas del evaluador. Escribe facts.json,
criteria.json y el journal en el directorio de caso y deja el veredicto a
creator_eval.evaluate_case, cuyo núcleo no cambia.

El journal que no se puede descubrir es un fallo cerrado: no se escribe
caso. También lo es una excepción inesperada del validador Host: es
infraestructura, no un veredicto sobre el prompt, y aborta la derivación
en lugar de puntuarse como prevalidación fallida. La inconsistencia entre
los hechos derivados y el journal la detecta después grade() como ABSTAIN,
nunca como PASS.
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
from acceptance_reviewer import tree_digest
from creator_client import dsh_home_candidates
from host_validator import validate_package

SESSION_USAGE_FIELDS = ("usage_input_tokens", "usage_output_tokens",
                        "usage_tokens", "usage_cache_read_tokens",
                        "usage_steps")


def resolve_dsh_home(explicit=None):
    """Resolve the DSH home: flag, then the client's own acquisition policy.

    El mismo home que usaría un proceso DSH recién lanzado: la política
    (env DSH_HOME primero, después los candidatos estándar) vive en
    creator_client y se reutiliza aquí en vez de reimplementarse. Sin
    candidato existente no hay home: el fallo es cerrado.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    for candidate in dsh_home_candidates():
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

    The run documents do not record the verdict, so it is observed again.
    The validator's own ValueError is its closed outcome about the package
    (no generated/, manifest missing or unreadable): the prevalidation did
    not pass. Any other exception is the validator's infrastructure failing,
    not a verdict about the prompt: it propagates as a closed derivation
    failure (exit 2, no case) instead of being scored as
    ``prevalidation_passed=False``.
    """
    try:
        report = validate(run_dir / "generated", run_dir=run_dir)
    except ValueError:
        return False
    except Exception as error:
        raise ValueError(
            "prevalidación Host falló de forma inesperada: "
            f"{type(error).__name__}: {error}") from error
    return bool(getattr(report, "passed", False))


def _product_tree_digest(project_root):
    """The framework tree digest of the run's product directory, or None.

    ``run.json`` records the identity the install derived — the sha256 of
    the commit revision, which varies between CI runs — but not the path of
    the product, so the digest comparable with the one registered in the
    product manifest (``acceptance_reviewer.tree_digest``, the framework's
    own convention) only exists when the caller supplies the root, as the
    workflow does with ``--project-root``. Absent root, absent field: the
    closed projection never invents an identity.
    """
    if not project_root:
        return None
    return tree_digest(project_root)


def derive_facts(run_dir, events, session, *, validate=None,
                 project_root=None):
    """Derive the recorded facts of a finished run from its own evidence.

    Absent sources are omitted, never invented: an incomplete run leaves the
    matching gap for grade() to abstain on. ``journal_event_count``, the
    frame accounting, the duration and the recorded-or-omit predicates reuse
    the evaluator's rules so facts and journal are held to one standard.
    """
    run_dir = Path(run_dir)
    run_doc, _ = creator_eval.read_json(run_dir / "run.json")
    creator_eval.require_dict(run_doc, "run.json")
    request, _ = creator_eval.read_json(run_dir / "generation-request.json")
    creator_eval.require_dict(request, "generation-request.json")
    creator_eval.require_dict(session, "creator-session.json")

    facts = {}

    def take(key, value):
        if value is not None:
            facts[key] = value

    take("generation_id",
         creator_eval.text_or_none(run_doc, "generation_id"))
    project = run_doc.get("project")
    if isinstance(project, dict):
        named = {}
        for key in ("name", "root_identity"):
            value = creator_eval.text_or_none(project, key)
            if value is not None:
                named[key] = value
        if named:
            facts["project"] = named
    take("framework_revision",
         creator_eval.text_or_none(run_doc, "framework_revision"))
    budget = run_doc.get("budget")
    if isinstance(budget, dict):
        facts["budget"] = dict(budget)
    take("prompt_version",
         creator_eval.text_or_none(request, "prompt_version"))

    for name in SESSION_USAGE_FIELDS:
        take(name, creator_eval.int_or_none(session, name))
    take("stop_reason", creator_eval.text_or_none(session, "reason"))
    if isinstance(session.get("terminal"), bool):
        facts["terminal_turn"] = session["terminal"]
    take("journal_last_seq", creator_eval.int_or_none(session, "cursor"))

    model = _model_from_events(events)
    if model:
        facts["model"] = model
    facts["turns_started"] = _turns_started(events)
    facts["journal_event_count"] = creator_eval.frame_count(events)
    take("elapsed_seconds", creator_eval.frame_span_seconds(events))
    take("product_tree_digest", _product_tree_digest(project_root))
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


def build_case(run_dir, case_dir, criteria, *, dsh_home=None, validate=None,
               project_root=None):
    """Derive the facts of one finished run and assemble its case directory.

    Writes facts.json, criteria.json and the discovered journal, in that
    order, after every closed failure has been ruled out: a run or journal
    that cannot be derived leaves the case directory untouched. The product
    root is optional: without it the facts carry no ``product_tree_digest``.
    Returns the derived facts.
    """
    criteria = creator_eval.require_criteria(criteria)
    run_dir = Path(run_dir)
    case_dir = Path(case_dir)
    session, _ = creator_eval.read_json(run_dir / "creator-session.json")
    creator_eval.require_dict(session, "creator-session.json")
    session_id = _require_session_id(session.get("session_id"))
    home = resolve_dsh_home(dsh_home)
    if home is None:
        raise ValueError(
            "Home de DSH no disponible: pasa --dsh-home o define DSH_HOME")
    journal = discover_journal(home, session_id)
    events, _ = creator_eval.read_events(journal, journal.name)
    facts = derive_facts(run_dir, events, session, validate=validate,
                         project_root=project_root)
    case_dir.mkdir(parents=True, exist_ok=True)
    creator_eval.write_report(
        case_dir / "facts.json",
        json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    creator_eval.write_report(
        case_dir / "criteria.json",
        json.dumps(criteria, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n")
    _copy_journal(journal, case_dir)
    return facts
