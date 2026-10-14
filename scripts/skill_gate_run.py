"""Run the compiled corpus against real modes, or say exactly why it cannot (E3).

The gate has been able to score observations since the corpus became
executable, and nothing has ever produced one, because producing them needs a
session and a provider that the operator configures. That is a real dependency
and this module does not pretend otherwise: with no authenticated DSH it
abstains and names the missing piece, in the same words the launcher uses, so
the two answers cannot disagree.

With a session, each compiled case is dispatched to the mode under test and the
verdict is read back from what the mode persisted. The observation is bound to
the corpus, the candidate and the compiler, because an unbound verdict is what
made the legacy gate unable to tell two runs apart.

The dispatch goes through the DSH session API that this release actually
exposes -- ``session/create`` for the mode, ``session/prompt`` for the case,
then the same ``creator_observation`` fold the acceptance reviewer uses to
know a turn is over. An earlier revision called an ``evaluator`` RPC endpoint
this release does not have: a call to a method that never existed answers a
404 at best and a fabricated verdict at worst, and it named no carency the
operator could fix. The prompt carries the case and nothing else: no expected
verdict, no corpus digest, no sibling case. A case that leaked its own answer
would measure reading.

What this module never does is invent a verdict. A case the mode did not answer
is `NOT_COVERED`, and the gate abstains rather than scoring a guess.

And it never buys a turn to learn something two RPCs already know. A generated
operational mode publishes a ``json mode-layout`` block naming an immutable
session root, and its first bash -- with no workdir -- is the check that it is
standing there. A per-case workspace is not that root: giving every case its own
subdirectory is precisely how one case is stopped from reading another's answer.
So before any ``session/create`` this runner requires an explicit, Host-owned
evaluator that verifies, per case, the layout and the effective skill
availability of the mode that case will be dispatched to -- and refuses the
whole run naming the missing piece when there is none, or when the adapter does
not cover every case. Fail closed, before the spend: an incompatible preset
gets ``RunnerUnavailable``, not 55 turns that end `NOT_COVERED`.

A case that is dispatched carries its task, its fixture and its evaluated
claim or action -- never the ``type`` label. Over this corpus the type nearly
determines the expected verdict, so sending it as a classification would hand
the model the answer. It never travels.

A missing evaluator is not evidence that the operational preset's layout or
skill catalogue is compatible. It is a named abstention, before any turn.
"""

import json
import hashlib
import re
import os as os_module
import stat as stat_module
import tempfile
import time
from pathlib import Path

import corpus_compiler

SCHEMA_VERSION = corpus_compiler.SCHEMA_VERSION
VERDICTS = ("PASS", "FAIL", "BLOCKED", "NOT_COVERED")
MAX_EVIDENCE = 1024
# The persisted answer is small: one verdict and its observation. The budget is
# applied by stat before reading, so a mode that writes a megabyte of noise next
# to the contract costs an inode read, not a real allocation.
RESULT_FILENAME = "result.json"
RESULT_MAX_BYTES = 64 * 1024
# A truncated observation has to announce itself: silently dropping the tail of
# an answer would make an edited evidence look like the one that arrived.
EVIDENCE_TRUNCATION_MARK = "…[recortada]"
# The workspace the mode is given has to live outside the canonical tree: a
# fixture that writes into the repo dirties the tree the gate is judging, and
# the run's answers would be mixed with the framework's own files.
RUN_DIR_MODE = 0o700
# A correlated turn/end is the only turn closure that counts as an answer.
# Turns that closed without producing anything the case asked for. They read
# like a turn end and act like one, so the fold has to treat the difference
# explicitly rather than letting them pass as completion.
ABORTED_TURN_TYPES = frozenset({"session/idle", "turn/cancel", "session/error",
                                "turn/error"})


class RunnerUnavailable(RuntimeError):
    """No session to run against. The message names the missing piece."""


class CompatibleEvaluator:
    """Host-owned evaluator adapter, not an RPC endpoint or a model claim.

    An operational preset's fixed session-root layout is incompatible with a
    fresh per-case workspace. DSH's preset roster confirms only the preset
    composition, not that each of the corpus's 25 skills is effectively loaded.
    The stock DSH client therefore cannot prepare this corpus. An explicit
    Host-owned adapter must check the *effective* mode, skill and per-case
    workspace layout before any session is created. ``prepare`` returns a
    case-id -> preset-id routing table after those checks; the runner checks
    completeness and the real preset roster, then uses the ordinary DSH
    session API. A failed check raises RunnerUnavailable and spends no turn.

    Subclasses must do real environment checks here (and provide a compatible
    case-directory preset). Merely echoing an agent's prompt or a declarative
    assertion of available skills is not a valid implementation.
    """

    require_skill_load = True

    def prepare(self, client, corpus, mode, root):
        raise RunnerUnavailable(
            "adaptador sin comprobación efectiva de layout y skill por caso")



class HostCorpusEvaluator(CompatibleEvaluator):
    """Read-only Host publication preflight; never claims runtime skill loading.

    The ACTIVE bundle and its inventory receipt bind the skill files to the
    published generation. The preset read binds its skill root to that bundle.
    Operational mode layouts still require the original session root, not an
    isolated case directory; in that situation this adapter refuses dispatch.
    """

    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def prepare(self, client, corpus, mode, root):
        import transaction

        managed = self.workspace / ".dsh-managed"
        active = managed / "ACTIVE"
        receipt_path = managed / "published-presets.json"
        if (not active.is_file() or active.is_symlink() or
                not receipt_path.is_file() or receipt_path.is_symlink()):
            raise RunnerUnavailable("publicación Host ACTIVE/receipt ausente")
        try:
            generation = active.read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]+", generation):
                raise ValueError("identificador ACTIVE inválido")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            bundle = managed / "bundles" / generation
            skills = bundle / "skills"
            transaction._safe_tree(bundle)
            if (receipt.get("generation_id") != generation or
                    receipt.get("bundle_path") != str(bundle) or
                    skills.is_symlink() or not skills.is_dir() or
                    receipt.get("sha256") != hashlib.sha256(json.dumps(
                        transaction._inventory(bundle), sort_keys=True
                    ).encode()).hexdigest()):
                raise ValueError("recibo/inventario no coincide con ACTIVE")
            document = client.read_agent_preset(mode)
            document = document.get("value", document)
            if document.get("agentPreset") != mode:
                raise ValueError("agentPresets/read no confirmó modo")
            content = document.get("content")
            if not isinstance(content, str):
                raise ValueError("composición ausente")
            # The published transaction config uses an exact absolute custom
            # root, never ambient/default roots or a self-reported skill list.
            import composition_contract
            with tempfile.TemporaryDirectory(prefix="gate-composition-") as temp:
                path = Path(temp) / "composition.yml"
                path.write_text(content, encoding="utf-8")
                rows = composition_contract.parse_composition(path)
            provider = [row for row in rows if row["name"] ==
                        "@deepseek-ai/dsh-skill-filesystem"]
            if len(provider) != 1:
                raise ValueError("proveedor de skills no único")
            lines = [line.strip() for line in provider[0]["lines"]]
            if lines[2:] != ["config:", "includeDefaultRoots: false",
                             "customSkillDirs:",
                             f"- {json.dumps(str(skills), ensure_ascii=False)}"]:
                raise ValueError("skill root publicado no coincide con ACTIVE")
            mode_skill = skills / mode / "SKILL.md"
            if (mode_skill.is_symlink() or not mode_skill.is_file() or
                    mode_skill.stat().st_nlink != 1):
                raise ValueError("SKILL.md del modo no disponible en ACTIVE")
            import layout_contract
            blocks = list(layout_contract._LAYOUT_BLOCK.finditer(
                mode_skill.read_text(encoding="utf-8")))
            if len(blocks) != 1:
                raise ValueError("mode-layout del modo ausente o ambiguo")
            layout = json.loads(blocks[0].group("body"))
            product = self.workspace.parent / layout.get("product_root", "")
            expected = layout_contract.layout_from_paths(product, self.workspace)
            if (layout != expected or not product.is_dir() or
                    product.is_symlink() or
                    self.workspace.is_symlink()):
                raise ValueError("mode-layout no coincide con producto/workspace Host")
            for case in corpus["cases"]:
                name = case["target_skill"]
                if (not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or
                        not (skills / name / "SKILL.md").is_file() or
                        (skills / name).is_symlink() or
                        (skills / name / "SKILL.md").is_symlink()):
                    raise ValueError(f"skill no disponible en bundle ACTIVE: {name}")
        except (OSError, ValueError, TypeError, KeyError, AttributeError,
                transaction.TransactionError) as error:
            raise RunnerUnavailable(f"preflight Host de skills no verificable: {error}") from error
        raise RunnerUnavailable(
            "skills disponibles en bundle ACTIVE, pero carga efectiva no observable "
            "antes de session/create; se requiere carga de skill comprobable por caso")


def resolve_session(client=None):
    """The authenticated DSH client, or the concrete reason there is none."""
    if client is not None:
        return client
    import creator_client

    try:
        resolved, origin = creator_client.acquire_dsh_client()
    except Exception as error:
        raise RunnerUnavailable(
            f"no hay sesión DSH utilizable: {type(error).__name__}: {error}") from error
    if resolved is None:
        raise RunnerUnavailable(f"no hay sesión DSH utilizable: {origin}")
    return resolved


def _verify_mode(client, mode, verified=None):
    """Verify the mode under test, or say exactly why it cannot be dispatched.

    The check is the one the campaign preflight already uses,
    ``workflow._verify_preset``: agentPresets/list + agentPresets/read with the
    exact operational composition. It is reused rather than reimplemented
    because a second reader of that contract is a second way to be wrong about
    it, and the composition is what decides whether a session can serve the
    framework's write contract at all.

    An empty mode, a preset the roster does not list, a broken preset and a
    composition that is not the exact one are all refusals: dispatching any of
    them would attribute the verdict to a mode nobody verified.

    ``verified`` is an optional set of modes already checked in this run; a
    second call for the same mode returns None without the two RPCs, which is
    what keeps fifty-five cases from verifying one preset fifty-five times.

    Returns None when the mode is verified, otherwise the detail naming the
    missing piece. A client that cannot be asked is also a refusal -- the mode
    was not verified, and "not verified" never dispatches.
    """
    if not isinstance(mode, str) or not mode.strip():
        return "--mode ausente o vacío: el corpus gate no despacha contra un modo sin nombre"
    mode = mode.strip()
    if len(mode) > 128:
        return f"mode demasiado largo ({len(mode)}): no es un preset declarable"
    if verified is not None and mode in verified:
        return None
    try:
        import workflow
    except ImportError as error:
        return f"no se puede verificar el preset: {error}"
    verify = getattr(workflow, "_verify_preset", None)
    if not callable(verify):
        return "workflow sin _verify_preset: composición de preset no verificable"
    for attribute in ("list_agent_presets", "read_agent_preset"):
        if not callable(getattr(client, attribute, None)):
            return (f"el cliente DSH no expone {attribute}: sin el roster de "
                    f"presets el modo bajo prueba no queda verificado")
    detail = verify(client, mode)
    if detail is not None:
        return f"preset no verificado {mode}: {detail}"
    if verified is not None:
        verified.add(mode)
    return None


def _dispatch(client, case, mode, timeout, workspace, verified=None,
              case_fd=None, workspace_check=None, require_skill_load=False):
    """Ask one mode to run one case and read back what it persisted.

    The path is the session API of DSH 0.2.0-rc.2, the same one the acceptance
    reviewer and the Creator use: a session is created for the mode under test
    over ``workspace``, the prompt carries the case and nothing else, and the
    verdict is read out of the object the mode itself persisted. A client that
    cannot serve one of those steps fails here naming the missing piece,
    instead of falling back to an ``evaluator`` endpoint this release does not
    have.

    The evaluator prompt carries the case and nothing else: no expected
    verdict, no corpus digest, no sibling case. A case that leaked its own
    answer would measure reading.

    ``verified`` is the per-run set of modes already checked against the
    roster. The check is two RPCs, and a corpus is fifty-five cases; without
    it the same verified preset would be asked again for every case.

    ``case_fd`` and ``workspace_check`` pin the directory the answer will be
    read from: the existence and identity check runs again immediately before
    the session is created (so a directory swapped for a symlink after the
    preflight refuses the case instead of dispatching into it), and the read of
    ``result.json`` is done through a fresh ``openat`` on that same descriptor,
    so the file the mode is told to write is the file this gate reads back.
    """
    for attribute in ("create_creator_session", "send_prompt",
                      "creator_observation"):
        if not callable(getattr(client, attribute, None)):
            raise RuntimeError(
                f"el cliente DSH no expone {attribute}: el corpus gate solo "
                f"despacha por la API de sesión real (session/create + "
                f"session/prompt + session/page); DSH 0.2.0-rc.2 no tiene "
                f"endpoint evaluator")
    if case_fd is not None and not workspace_check():
        raise RuntimeError(
            "el directorio del caso fue sustituido antes de session/create: "
            "la respuesta no se leería del lugar donde se pidió escribirla")
    detail = _verify_mode(client, mode, verified)
    if detail is not None:
        # No dispatch without a verified preset. An empty or unknown mode would
        # be answered by whatever default session the Host boots, and the
        # resulting verdict would be bound to a mode nobody named.
        raise RuntimeError(detail)
    session_id = None
    try:
        session_id = client.create_creator_session(
            workspace_path=workspace, agent_preset=mode)
        client.send_prompt(session_id, json.dumps({
            "case": _case_scenario(case),
            "answer": {
                "file": "result.json",
                "schema": {
                    "verdict": "PASS|FAIL|BLOCKED|NOT_COVERED",
                    "evidence": "what you observed, verbatim and specific",
                },
                "instruction": (
                    "Judge only the candidate's own behaviour against the "
                    "task. Write exactly one JSON object with exactly the "
                    "fields above to result.json using workflow_write, and "
                    "write no other file. NOT_COVERED is for a case you could "
                    "not run, never a substitute for FAIL."
                ),
            },
        }, ensure_ascii=False))
        return _verdict_from(_read_mode_verdict(
            client, session_id, timeout, workspace, case_fd=case_fd,
            workspace_check=workspace_check,
            target_skill=case["target_skill"] if require_skill_load else None))
    finally:
        # A dispatched case never stays live: the corpus is a sequence of
        # independent turns, and an orphaned one holds quota and workspace.
        if session_id is not None:
            cancel = getattr(client, "cancel_session", None)
            if callable(cancel):
                try:
                    cancel(session_id)
                except Exception:
                    pass


def _case_scenario(case):
    """The case exactly as the mode receives it: the task, never the answer.

    Everything the compiler marked public travels, so the mode judges the
    scenario's own conditions rather than a generic abstraction of them. What
    never travels is the *classification label*. ``case["type"]`` is not
    metadata: over this corpus it nearly determines the expected verdict -- a
    "negative" case is FAIL or BLOCKED, a "positive" one is PASS -- so sending
    it lets a model read the answer out of the label instead of doing the work.
    The task, the fixture and the evaluated claim/action describe the situation
    without saying which side of the boundary the Host expects, which is what
    the case is actually asking.

    The compiler is the one that decided those keys are public, so this does not
    copy a second list of allowed fields and drift from it: the oracle keys are
    excluded by name, and everything else the case carries is the case's own.
    """
    public = case["input"]
    forbidden = corpus_compiler.ORACLE_FIELDS
    if forbidden & set(public):
        raise RunnerUnavailable("el input público contiene un oráculo")
    sent = {"case_id": case["case_id"]}
    sent.update(public)
    # ``target`` is the skill name. It stays because a mode cannot load a skill
    # it was not named; it is the case's subject, not its verdict.
    return sent


def _skill_loaded(events, name):
    """Only a matched successful DSH tool-skill load is runtime evidence."""
    calls = set()
    for event in events:
        if event.get("type") not in ("tool/call", "tool/result"):
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event["type"] == "tool/call":
            try:
                args = json.loads(data.get("arguments", ""))
            except (TypeError, ValueError):
                continue
            if (data.get("name") == "skill" and isinstance(args, dict) and
                    args.get("name") == name and isinstance(data.get("callId"), str)):
                calls.add((data.get("turn"), data["callId"]))
        else:
            message = data.get("message")
            if (not data.get("error") and isinstance(message, dict) and
                    message.get("isError") is False and
                    (data.get("turn"), message.get("toolCallId")) in calls):
                return True
    return False


def _read_mode_verdict(client, session_id, timeout, workspace,
                       case_fd=None, workspace_check=None, target_skill=None):
    """What the mode persisted for this turn, or nothing to read.

    The fold is the one ``creator_client`` uses for a Creator turn, so the
    shapes are the ones DSH really emits: a flat ``events`` list of
    ``{"seq", "type", "data"}`` records, ``turn/start`` opening the turn and
    ``turn/end`` closing it under the same turn number.

    The answer is read ONLY from the object the mode wrote into the case
    workspace -- the same file contract the acceptance reviewer reads its
    actor's result from. There is deliberately no fallback to the trailing
    assistant text: a turn that ended without the mode writing its object
    leaves nothing to parse, and that is NOT_COVERED rather than a guess; so
    does a turn that never closed before the deadline, and so does a file the
    mode wrote but that does not satisfy the contract.

    Narrated PASS never counts. The assistant transcript is the mode telling a
    story about its own work; a model that says "listo, todo bien" in prose
    while leaving no persisted object has produced evidence of prose, not an
    observation, and a gate that accepts prose measures eloquence.

    A turn that aborted -- ``session/idle``, ``turn/cancel``, an error event --
    closes the fold without an answer and returns None like a timeout does. It
    used to be folded as a successful close, so a case the mode never answered
    was scored from whatever file the directory happened to hold. An aborted
    turn and an unanswered turn are the same fact: the case was not covered.
    """
    deadline = time.monotonic() + max(1, timeout)
    cursor = -1
    events = []
    while time.monotonic() < deadline:
        observation = client.creator_observation(session_id, cursor=cursor)
        if not isinstance(observation, dict):
            continue
        if isinstance(observation.get("cursor"), int):
            cursor = max(cursor, observation["cursor"])
        for event in observation.get("events") or []:
            if isinstance(event, dict):
                events.append(event)
        aborted = _turn_aborted(events)
        if aborted is not None or _turn_ended(events):
            # Read back what the mode persisted. None means it did not persist
            # an object satisfying the contract, and _verdict_from turns that
            # into an explicit NOT_COVERED naming what was missing. An aborted
            # turn reaches here with the same None and the same honesty.
            if aborted is not None:
                return None
            if target_skill is not None and not _skill_loaded(events, target_skill):
                return None
            if workspace_check is not None and not workspace_check():
                return None
            return _persisted_verdict(workspace, case_fd=case_fd)
    # The deadline ran out before the turn closed. Reading a half-written
    # answer would be inventing one, so the caller gets NOT_COVERED.
    return None


def _persisted_verdict(workspace, case_fd=None):
    """The verdict object the mode wrote into the case workspace, or None.

    This is the same contract ``acceptance_reviewer`` reads: the mode is told to
    write exactly one JSON object to ``result.json`` and to write nothing else.
    Reading it back is reading what the mode persisted, not inferring what it
    meant, which is the whole difference between an observation and an opinion.

    The read is confined the way the sibling readers are (``campaign`` and
    ``acceptance_reviewer``): the byte budget is applied by stat before a single
    byte is read, symlinks are refused outright, and the resolved path has to
    stay inside the case workspace. A mode under test writes inside its own
    directory; a ``result.json`` that resolves outside it is following a link or
    a parent traversal out of the workspace the case was given, which is the
    read primitive the fixture must not expose.

    Nothing here ever falls back to the assistant text. A file that is present
    but unreadable -- oversized, corrupt, a link, out of bounds -- is a case the
    mode did not answer in the shape promised, so it lands in NOT_COVERED with
    the reason, exactly as a missing file does.
    """
    if not workspace:
        return None
    case_dir = Path(workspace)
    try:
        if case_fd is not None:
            # The directory descriptor was opened at exclusive creation and
            # checked against the case path before session/create and again
            # before this read. openat with O_NOFOLLOW makes final-component
            # symlink swaps fail even between stat and open.
            flags = os_module.O_RDONLY | os_module.O_NOFOLLOW | os_module.O_NONBLOCK
            fd = os_module.open(RESULT_FILENAME, flags, dir_fd=case_fd)
            with os_module.fdopen(fd, "rb") as stream:
                stat = os_module.fstat(stream.fileno())
                if not _stat_is_regular_file(stat) or stat.st_size > RESULT_MAX_BYTES:
                    return None
                data = stream.read(RESULT_MAX_BYTES + 1)
        else:
            # Direct callers of this reader keep the same confinement as the
            # runner's path; the runner itself always supplies the pinned fd.
            case_dir = case_dir.resolve()
            path = case_dir / RESULT_FILENAME
            if path.is_symlink() or not path.resolve().is_relative_to(case_dir):
                return None
            stat = path.stat(follow_symlinks=False)
            if not _stat_is_regular_file(stat) or stat.st_size > RESULT_MAX_BYTES:
                return None
            with open(path, "rb", opener=_no_follow_opener) as stream:
                data = stream.read(RESULT_MAX_BYTES + 1)
    except (OSError, ValueError):
        return None
    if len(data) > RESULT_MAX_BYTES:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _stat_is_regular_file(stat):
    """A regular file, not a device, a socket or a fifo that answers stat."""
    return stat_module.S_ISREG(stat.st_mode)


def _no_follow_opener(path, flags):
    """An opener that refuses to follow a symlink on the final component.

    ``O_NOFOLLOW`` is what makes the read single-syscall safe: the check in
    ``_persisted_verdict`` cannot be raced between stat and open, so the mode
    under test cannot hand back a verdict it does not deserve to give.
    """
    flags |= getattr(os_module, "O_NOFOLLOW", 0)
    return os_module.open(path, flags)


def _turn_ended(events):
    """Whether the observed fold saw a turn open and then close.

    Shape verified against ``creator_client._fold_observation``: ``turn/start``
    carries the turn number in ``data.turn`` and ``turn/end`` repeats it.
    """
    open_turn = None
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("type") == "turn/start":
            open_turn = data.get("turn")
        elif (event.get("type") == "turn/end" and
                open_turn is not None and data.get("turn") == open_turn):
            return True
    return False


def _turn_aborted(events):
    """The reason a turn closed without producing an answer, or None.

    ``session/idle`` and ``turn/cancel`` are not completions: they say the turn
    stopped for a reason outside the case. They used to be folded by
    ``_turn_ended`` as if they were a close, so the very next file the
    directory held became that case's verdict -- an answer written by a previous
    run, or by nobody at all. An aborted turn is indistinguishable from an
    unanswered one, and the gate reports both the same honest way.
    """
    for event in reversed(events):
        event_type = event.get("type")
        if event_type in ABORTED_TURN_TYPES:
            return event_type
        if event_type == "turn/end":
            data = event.get("data")
            reason = data.get("reason") if isinstance(data, dict) else None
            if isinstance(reason, str) and any(
                    word in reason.lower() for word in
                    ("cancel", "error", "fail", "abort", "interrupt")):
                return reason
    return None


def _verdict_from(response):
    """The only shapes that count. Anything else is NOT_COVERED, not a guess."""
    if not isinstance(response, dict):
        return "NOT_COVERED", "respuesta no es un objeto"
    verdict = response.get("verdict")
    evidence = response.get("evidence")
    if verdict not in VERDICTS:
        return "NOT_COVERED", f"veredicto ausente o inválido: {verdict!r}"
    if not isinstance(evidence, str) or not evidence.strip():
        return "NOT_COVERED", "observación sin evidencia"
    # The bound answer is bounded in success too, not only in failure: the
    # observation file is read by the gate and published with the report, so a
    # mode that answers PASS with a megabyte of prose has to be truncated on
    # the way in rather than carried into the artifact. Truncation stays
    # visible -- the observation says it was cut.
    evidence = evidence.strip()
    room = MAX_EVIDENCE - len(EVIDENCE_TRUNCATION_MARK)
    if len(evidence) > MAX_EVIDENCE and room > 0:
        return verdict, evidence[:room] + EVIDENCE_TRUNCATION_MARK
    if len(evidence) > MAX_EVIDENCE:
        # No room for the mark: keep the head of the budget rather than
        # producing a slice that is longer than the bound it answers to.
        return verdict, evidence[:MAX_EVIDENCE]
    return verdict, evidence


def _external_root(workspace):
    """Validate the caller's parent before any case is created.

    Existing roots must be actual directories, not symlinks (including their
    ancestors), and must not be inside the canonical repository. Keep an fd to
    the checked inode for all exclusive mkdir/open operations below.
    """
    # abspath removes '..' lexically without resolving links. Walk from '/' with
    # O_NOFOLLOW at *every* component, not just the final one; resolving the
    # parent by pathname and opening it later left an ancestor-symlink race.
    root = Path(os_module.path.abspath(os_module.fspath(workspace)))
    canonical = Path(__file__).resolve().parents[1]
    if root == Path("/") or root == canonical or canonical in root.parents:
        raise RunnerUnavailable("workspace de casos dentro del repositorio canónico o raíz /")
    flags = os_module.O_RDONLY | os_module.O_DIRECTORY | os_module.O_NOFOLLOW
    parent_fd = os_module.open("/", flags)
    try:
        for component in root.parent.parts[1:]:
            next_fd = os_module.open(component, flags, dir_fd=parent_fd)
            os_module.close(parent_fd)
            parent_fd = next_fd
        try:
            os_module.mkdir(root.name, mode=RUN_DIR_MODE, dir_fd=parent_fd)
        except FileExistsError:
            pass
        entry = os_module.stat(root.name, dir_fd=parent_fd,
                               follow_symlinks=False)
        if not stat_module.S_ISDIR(entry.st_mode):
            raise RunnerUnavailable(f"workspace con symlink o no directorio: {root}")
        fd = os_module.open(root.name, flags, dir_fd=parent_fd)
    except OSError as error:
        # The component walked under dir_fd was a symlink, missing or not a
        # directory. Nothing has been created inside the canonical repository.
        raise RunnerUnavailable(f"workspace externo inválido o con symlink: {root}: {error}") from error
    finally:
        os_module.close(parent_fd)
    st = os_module.fstat(fd)
    if ((st.st_dev, st.st_ino) != (entry.st_dev, entry.st_ino)
            or st.st_uid != os_module.getuid() or st.st_mode & 0o077):
        os_module.close(fd)
        raise RunnerUnavailable(f"workspace sustituido o no privado del Host: {root}")
    return root, fd


def _fresh_case_dir(root, root_fd, case_id):
    """Exclusively create one case in the pinned root; never reuse old output."""
    if not corpus_compiler._is_case_id(case_id):
        raise RunnerUnavailable(f"case_id inseguro: {case_id!r}")
    try:
        os_module.mkdir(case_id, mode=0o700, dir_fd=root_fd)
        fd = os_module.open(case_id, os_module.O_RDONLY | os_module.O_DIRECTORY |
                            os_module.O_NOFOLLOW, dir_fd=root_fd)
    except OSError as error:
        raise RunnerUnavailable(
            f"directorio del caso {case_id!r} no es nuevo y exclusivo: {error}") from error
    if not _same_workspace(root, root_fd, case_id, fd):
        os_module.close(fd)
        raise RunnerUnavailable(f"directorio del caso {case_id!r} sustituido tras mkdir")
    return root / case_id, fd


def _same_workspace(root, root_fd, case_id, case_fd):
    """Detect replaced roots/cases before session/create and before file read."""
    try:
        current_root = os_module.stat(root, follow_symlinks=False)
        current_case = os_module.stat(case_id, dir_fd=root_fd,
                                      follow_symlinks=False)
        return (stat_module.S_ISDIR(current_root.st_mode)
                and stat_module.S_ISDIR(current_case.st_mode)
                and (current_root.st_dev, current_root.st_ino) ==
                    (os_module.fstat(root_fd).st_dev, os_module.fstat(root_fd).st_ino)
                and (current_case.st_dev, current_case.st_ino) ==
                    (os_module.fstat(case_fd).st_dev, os_module.fstat(case_fd).st_ino))
    except OSError:
        return False


def _dispatch_route(evaluator, client, corpus, mode, root):
    """Require an explicit Host evaluator of layout and effective skills.

    DSH's operational preset has a fixed session-root startup check, while the
    corpus requires a fresh case cwd. A roster entry proves composition only,
    not that any one of the 25 target skills is actually discoverable. Without
    a compatible evaluator that checks both, there is no honest score to post.
    """
    try:
        route = evaluator.prepare(client, corpus, mode, root)
    except RunnerUnavailable:
        raise
    except Exception as error:
        raise RunnerUnavailable(
            f"adaptador no pudo verificar ruta/layout/skills: "
            f"{type(error).__name__}: {error}") from error
    ids = {case["case_id"] for case in corpus["cases"]}
    if not isinstance(route, dict) or set(route) != ids or any(
            not isinstance(value, str) or not value.strip()
            for value in route.values()):
        raise RunnerUnavailable("adaptador no verificó ruta/layout/skill de todos los casos")
    return route


def run_corpus(client, corpus, *, mode, candidate_digest, provider_name,
               timeout=900, on_case=None, workspace=None, _temp=None,
               evaluator=None):
    """Run only against a compatible Host evaluator; otherwise abstain pre-spend.

    The adapter verifies effective per-skill availability and a compatible
    per-case cwd before any session is created. The built-in DSH preset/session
    API cannot establish either: a single operational preset cannot count as
    testing all 25 skills. The observation stays bound to this corpus/candidate.
    """
    corpus_compiler.validate_corpus(corpus)
    if not isinstance(mode, str) or not mode.strip():
        raise RunnerUnavailable("--mode ausente o vacío")
    for attribute in ("list_agent_presets", "read_agent_preset",
                      "create_creator_session", "send_prompt",
                      "creator_observation"):
        if not callable(getattr(client, attribute, None)):
            raise RunnerUnavailable(
                f"el cliente DSH no expone {attribute}: no se puede verificar "
                "el preset ni ejecutar un caso")
    if evaluator is None or not callable(getattr(evaluator, "prepare", None)):
        raise RunnerUnavailable(
            "preset operacional incompatible: cwd/layout fijo y 25 skills del "
            "corpus sin disponibilidad efectiva verificada; falta adaptador "
            "evaluador Host por caso (no existe endpoint evaluator DSH)")
    created = None
    if workspace is None:
        created = _temp or tempfile.TemporaryDirectory(prefix="gate-run-")
        workspace = created.name
    observations = []
    try:
        root, root_fd = _external_root(workspace)
        try:
            route = _dispatch_route(evaluator, client, corpus, mode, root)
            verified = set()
            # Verify every routed preset before the first model turn.
            for preset in set(route.values()):
                detail = _verify_mode(client, preset, verified)
                if detail is not None:
                    raise RunnerUnavailable(detail)
            case_dirs = []
            try:
                # Prepare all workspaces and check every effective skill/layout
                # before *any* session/create. A partial corpus is not a score.
                for case in corpus["cases"]:
                    path, fd = _fresh_case_dir(root, root_fd, case["case_id"])
                    case_dirs.append((case, path, fd))
                    if not _same_workspace(root, root_fd, case["case_id"], fd):
                        raise RunnerUnavailable("workspace del caso sustituido por symlink")
                    verify = getattr(evaluator, "verify_case", None)
                    if not callable(verify):
                        raise RunnerUnavailable(
                            "adaptador sin verify_case de layout y skill efectiva")
                    try:
                        verified_case = verify(
                            client, case, route[case["case_id"]], path)
                    except RunnerUnavailable:
                        raise
                    except Exception as error:
                        raise RunnerUnavailable(
                            f"adaptador no pudo verificar layout y skill efectiva "
                            f"{case['target_skill']!r} para {case['case_id']}: "
                            f"{type(error).__name__}: {error}") from error
                    if verified_case is not True:
                        raise RunnerUnavailable(
                            f"adaptador no verificó layout y skill efectiva "
                            f"{case['target_skill']!r} para {case['case_id']}")
                for case, path, fd in case_dirs:
                    if not _same_workspace(root, root_fd, case["case_id"], fd):
                        raise RunnerUnavailable("workspace del caso sustituido antes de session/create")
                    try:
                        verdict, evidence = _dispatch(
                            client, case, route[case["case_id"]], timeout, path,
                            verified=verified, case_fd=fd,
                            require_skill_load=getattr(
                                evaluator, "require_skill_load", False),
                            workspace_check=lambda case_id=case["case_id"],
                            pinned_fd=fd: _same_workspace(
                                root, root_fd, case_id, pinned_fd))
                    except RunnerUnavailable:
                        raise
                    except Exception as error:
                        verdict, evidence = "NOT_COVERED", (
                            f"{type(error).__name__}: {error}"[:MAX_EVIDENCE])
                    observations.append({"case_id": case["case_id"],
                                         "verdict": verdict, "evidence": evidence})
                    if on_case is not None:
                        on_case(case, verdict, evidence)
            finally:
                for _, _, fd in case_dirs:
                    os_module.close(fd)
        finally:
            os_module.close(root_fd)
    finally:
        if created is not None:
            created.cleanup()
    return {"schema_version": SCHEMA_VERSION,
            "compiler_version": corpus["compiler_version"],
            "corpus_digest": corpus["corpus_digest"],
            "candidate_digest": candidate_digest,
            "provider": {"status": "available", "name": provider_name},
            "observations": observations}


def write_observations(payload, path):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     indent=2) + "\n", encoding="utf-8")
    return path


def abstain(reason):
    """The observation set a run with no session produces: none at all.

    Not an empty list scored as zero accuracy -- an unavailable provider cannot
    claim observations, and the gate abstains instead of judging.
    """
    return {"provider": {"status": "unavailable"}, "reason": reason}
