"""Sesiones DSH Host para evaluación y revisión independiente de aceptación.

Los actores producen observaciones estructuradas en workspaces separados. No
emiten ACTIVE ni escriben en el run/candidato canónico: el Host valida sus
resultados y calcula el veredicto determinista en acceptance.py.
"""
import hashlib
import inspect
import json
import shutil
import tempfile
import time
from pathlib import Path

from creator_client import acquire_dsh_client

SCHEMA_VERSION = 1


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root):
    """Stable digest of relative path, file digest and byte size."""
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink no permitido en candidato: {path}")
        if path.is_file():
            entries.append({
                "path": str(path.relative_to(root)),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            })
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _copy_readonly(source, target):
    source, target = Path(source), Path(target)
    shutil.copytree(source, target)
    for item in [target, *target.rglob("*")]:
        mode = item.stat().st_mode
        item.chmod(mode & ~0o222)


def _write_input(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o400)


def _load_result(path, *, expected_actor, expected_generation, expected_digest):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Resultado DSH ausente: {path}")
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Resultado DSH excede 1 MiB")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Resultado DSH no es JSON válido: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Resultado DSH debe ser objeto")
    required = {"schema_version", "actor", "generation_id", "candidate_digest", "verdict", "results", "summary"}
    if set(value) != required:
        raise ValueError(f"Campos de resultado DSH inválidos: {sorted(set(value) ^ required)}")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("schema_version de resultado DSH inválida")
    if value["actor"] != expected_actor:
        raise ValueError("Actor DSH no coincide")
    if value["generation_id"] != expected_generation:
        raise ValueError("Generación DSH no coincide")
    if value["candidate_digest"] != expected_digest:
        raise ValueError("Digest de candidato DSH no coincide")
    if value["verdict"] not in ("PASS", "FAIL", "BLOCKED", "UNVERIFIED"):
        raise ValueError("Veredicto DSH inválido")
    if not isinstance(value["results"], list) or not value["results"]:
        raise ValueError("Resultado DSH sin observaciones")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("Resultado DSH sin resumen")
    return value


class DshAcceptanceActors:
    """Run evaluator and reviewer in isolated temporary workspace roots."""

    def __init__(self, run_dir, *, client=None, launch=False, timeout_seconds=900):
        self.run_dir = Path(run_dir)
        self.generated = self.run_dir / "generated"
        self.client = client
        self.launch = launch
        self.timeout_seconds = timeout_seconds
        self._temp = None

    def __enter__(self):
        parent = self.run_dir / "acceptance" / "actors"
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix="host-actors-", dir=parent)
        return self

    def __exit__(self, *_args):
        if self._temp is not None:
            self._temp.cleanup()

    def _client(self):
        if self.client is not None:
            return self.client
        client, reason = acquire_dsh_client(launch=self.launch)
        if client is None:
            raise ValueError(f"Revisor DSH no disponible: {reason}")
        self.client = client
        return client

    def _workspace(self, actor, payload):
        if self._temp is None:
            raise RuntimeError("DshAcceptanceActors requiere context manager")
        workspace = Path(self._temp.name) / actor
        workspace.mkdir(mode=0o700)
        _copy_readonly(self.generated, workspace / "candidate")
        _write_input(workspace / "input.json", payload)
        return workspace

    @staticmethod
    def _call_session_method(method, session_id, **optional):
        """Call lifecycle helpers while tolerating older FakeClient signatures."""
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        kwargs = {name: value for name, value in optional.items()
                  if name in parameters}
        return method(session_id, **kwargs)

    @staticmethod
    def _fold_lifecycle(status, state):
        """Fold exact request-to-turn correlation and transitive quiescence."""
        value = status
        for _depth in range(4):
            if not isinstance(value, dict):
                return None
            if isinstance(value.get("running"), bool):
                break
            value = next((value[key] for key in
                          ("value", "session", "status", "result")
                          if isinstance(value.get(key), dict)), None)
        if not isinstance(value, dict) or not isinstance(value.get("running"), bool):
            return None

        children = value.get("children", [])
        jobs = value.get("jobs", [])
        events = value.get("events", [])
        if not all(isinstance(items, list)
                   for items in (children, jobs, events)):
            return None

        request_turn = state.get("request_turn")
        terminal = bool(state.get("terminal"))
        cursor = state.get("cursor", -1)
        for event in events:
            if not isinstance(event, dict):
                continue
            seq = event.get("seq")
            if isinstance(seq, int):
                cursor = max(cursor, seq)
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            if event.get("type") == "user/message":
                source = data.get("source")
                if (isinstance(source, dict) and
                        source.get("rpcId") == state["request_id"] and
                        isinstance(data.get("turn"), int)):
                    request_turn = data["turn"]
            elif (event.get("type") == "turn/end" and
                  request_turn is not None and
                  data.get("turn") == request_turn):
                terminal = True

        observed_cursor = value.get("cursor")
        if isinstance(observed_cursor, int):
            cursor = max(cursor, observed_cursor)
        child_running = any(
            not isinstance(child, dict) or child.get("running") is not False
            for child in children)
        active_jobs = any(
            not isinstance(job, dict) or
            job.get("status") in (None, "running", "stopping")
            for job in jobs)
        quiescent = not value["running"] and not child_running and not active_jobs
        state.update({
            "cursor": cursor,
            "request_turn": request_turn,
            "terminal": terminal,
            "quiescent": quiescent,
        })
        return state

    def _session_lifecycle(self, client, session_id, state):
        observe = getattr(client, "creator_observation", None)
        if callable(observe):
            observation = self._call_session_method(
                observe, session_id, cursor=state.get("cursor", -1))
            return self._fold_lifecycle(observation, state)
        return None

    def _wait_terminal(self, client, session_id, state, deadline):
        """Wait using lifecycle APIs, retaining correlation between observations."""
        remaining = max(0, deadline - time.time())
        for name in ("wait_for_session", "wait_session", "wait_for_terminal"):
            method = getattr(client, name, None)
            if callable(method):
                status = self._call_session_method(
                    method, session_id, timeout=remaining,
                    timeout_seconds=remaining)
                lifecycle = self._fold_lifecycle(status, state)
                if lifecycle is not None:
                    return lifecycle
                break
        return self._session_lifecycle(client, session_id, state)

    def _cancel_and_confirm(self, client, session_id, actor, state):
        if state.get("cancelled"):
            raise ValueError(
                f"Sesión DSH {actor} ya fue cancelada sin cierre confirmado "
                f"(session_id={session_id})")
        cancel = getattr(client, "cancel_session", None)
        if not callable(cancel):
            raise ValueError(
                f"Sesión DSH {actor} no pudo cerrarse: el cliente no soporta "
                f"cancel_session (session_id={session_id})")
        state["cancelled"] = True
        cancel(session_id)
        lifecycle = self._wait_terminal(
            client, session_id, state, time.time() + 5)
        if lifecycle is None or not lifecycle["quiescent"]:
            raise ValueError(
                f"Sesión DSH {actor} no pudo confirmar cierre tras cancelación; "
                f"se exige running:false y quiescencia de hijos/jobs "
                f"(session_id={session_id})")

    def _close_before_error(self, client, session_id, actor, state, error):
        """Never abandon a dispatched session whose quiescence is unproven."""
        if not state.get("quiescent"):
            self._cancel_and_confirm(client, session_id, actor, state)
        raise error

    def _send_prompt(self, client, session_id, prompt, request_id):
        send = client.send_prompt
        try:
            parameters = inspect.signature(send).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "request_id" in parameters:
            return send(session_id, prompt, request_id=request_id)
        return send(session_id, prompt)

    def _run(self, actor, payload, prompt):
        generation_id = payload["generation_id"]
        candidate_digest = payload["candidate_digest"]
        workspace = self._workspace(actor, payload)
        client = self._client()
        session_id = client.create_creator_session(
            workspace_path=workspace, agent_preset="standard")
        output_contract = f"""

Write exactly one final JSON object to result.json using workflow_write. Do not
write any other file. The object MUST have exactly these top-level fields:
{{"schema_version":1,"actor":{json.dumps(actor)},
 "generation_id":{json.dumps(generation_id)},
 "candidate_digest":{json.dumps(candidate_digest)},
 "verdict":"PASS"|"FAIL"|"BLOCKED"|"UNVERIFIED",
 "results":[{{"case_id":"...","verdict":"PASS"|"FAIL",
 "evidence":["candidate/relative/path"],"detail":"..."}}],
 "summary":"..."}}
Never emit ACTIVE/RETAINED and never call acceptance or transaction tools.
"""
        request_id = hashlib.sha256(
            f"acceptance:{generation_id}:{candidate_digest}:{actor}".encode("utf-8")
        ).hexdigest()
        self._send_prompt(client, session_id, prompt + output_contract, request_id)
        result_path = workspace / "result.json"
        deadline = time.time() + self.timeout_seconds
        state = {
            "request_id": request_id,
            "request_turn": None,
            "cursor": -1,
            "terminal": False,
            "quiescent": False,
            "cancelled": False,
        }
        while time.time() < deadline:
            try:
                lifecycle = self._session_lifecycle(client, session_id, state)
            except Exception as error:
                self._close_before_error(
                    client, session_id, actor, state,
                    ValueError(f"Error observando sesión DSH {actor}: {error}"))
            if lifecycle is not None and lifecycle["terminal"]:
                if not lifecycle["quiescent"]:
                    time.sleep(min(0.1, max(0, deadline - time.time())))
                    continue
                if not result_path.is_file():
                    self._close_before_error(
                        client, session_id, actor, state,
                        ValueError(
                            f"Sesión DSH {actor} terminó sin result.json "
                            f"(session_id={session_id})"))
                try:
                    result = _load_result(
                        result_path,
                        expected_actor=actor,
                        expected_generation=generation_id,
                        expected_digest=candidate_digest,
                    )
                except Exception as error:
                    self._close_before_error(
                        client, session_id, actor, state, error)
                return {
                    "session_id": session_id,
                    "workspace": str(workspace),
                    "result": result,
                }
            time.sleep(min(0.1, max(0, deadline - time.time())))
        self._cancel_and_confirm(client, session_id, actor, state)
        raise ValueError(
            f"Sesión DSH {actor} agotó {self.timeout_seconds}s; cancelada y "
            f"cerrada con running:false (session_id={session_id})")

    def evaluate(self, payload, prompt):
        return self._run("host-evaluator", payload, prompt)

    def review(self, payload, prompt):
        return self._run("host-independent-reviewer", payload, prompt)
