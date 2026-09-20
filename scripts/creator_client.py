"""Automatización DSH Creator — C2.

Cliente Host-side que crea una sesión Creator, envía el prompt versionado
y supervisa la generación sin persistir credenciales ni auto-aprobarse.

    python3 -B scripts/creator_client.py --run-dir <creator-runs/gen-id>

Versión: 1
"""

import base64
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import selectors
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK / "scripts"))

from onboard import checked

SCHEMA_VERSION = 1


class HostPrevalidationFailed(ValueError):
    """Creator output exists but must be rejected by Host acceptance."""


_DSH_URL_RE = re.compile(r"dsh web:\s+(https?://[^\s]+)")

PROMPT_VERSION = "1.0.0"

PROMPT_TYPES = (
    "initial_onboarding",
    "material_change_regeneration",
    "framework_update",
    "repair_retained",
    "skill_lifecycle",
)

CREATOR_INTERNAL_CAPABILITIES = [
    "project-discovery",
    "project-documenter",
    "contract-risk-mapper",
    "capability-partitioner",
    "capability-designer",
    "scenario-author",
    "skill-generator",
    "generation-repair",
    "drift-analyzer",
]

SKILL_SELECTION_ORDER = [
    "base-library",
    "specialized-catalog",
    "composition",
    "override",
    "extension",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_json(path):
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise ValueError(f"Archivo ausente o enlace simbólico: {path}")
    if p.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Archivo excesivo: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _atomic_json(path, value, *, exclusive=False):
    """Write JSON atomically without exposing a missing or partial state."""
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if exclusive and p.exists():
        raise FileExistsError(str(p))
    tmp = p.parent / ("." + p.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and p.exists():
            raise FileExistsError(str(p))
        os.replace(tmp, p)
        dir_fd = os.open(p.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _write_json(path, value):
    _atomic_json(path, value, exclusive=True)


def _update_json(path, value):
    """Atomically replace a Host-owned JSON status file."""
    _atomic_json(path, value)


@contextlib.contextmanager
def _run_lock(run_dir):
    """Serialize Creator supervision for one run across Host processes."""
    lock_path = Path(run_dir) / ".creator.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _library_selection_section():
    """Render the materialized library for the selection strategy.

    Fail-closed: an absent or invalid library document stops prompt
    building instead of silently omitting selection inputs.
    """
    library_path = FRAMEWORK / "library" / "library.json"
    if not library_path.is_file() or library_path.is_symlink():
        raise ValueError(f"Biblioteca materializada ausente: {library_path}")
    import generation_contracts as gc
    doc = _read_json(library_path)
    gc.validate("library", doc)
    digest = hashlib.sha256(library_path.read_bytes()).hexdigest()
    lines = [
        "## Biblioteca disponible",
        "",
        f"**Digest de biblioteca:** {digest}",
        "",
        "### Base inmutable (capa 1)",
    ]
    for b in doc["base_skills"]:
        lines.append(f"- `{b['name']}` — {b['purpose']}")
        if b.get("applicability"):
            lines.append(f"  - aplica: {b['applicability']}")
    if doc["catalog_patterns"]:
        lines.append("")
        lines.append("### Catálogo especializado (capa 2 — solo con señales observadas)")
        for c in doc["catalog_patterns"]:
            lines.append(f"- `{c['name']}` [{c['domain']}] — {c['purpose']}")
            for crit in c["activation_criteria"]:
                lines.append(f"  - activar si: {crit}")
    lines += [
        "",
        "Al reutilizar declara `reuse_source` y `reuse_reference` con el nombre exacto de la entrada usada. "
        "Un patrón de catálogo sin sus señales de activación observadas en el proyecto no se selecciona. "
        "Una extensión nueva exige justificar por qué no aplican las entradas anteriores y no declara `reuse_reference`.",
    ]
    return "\n".join(lines)


def _run_workspace(run_dir):
    """The run's workspace root: the parent of ``creator-runs/`` (§5 layout)."""
    run_dir = Path(run_dir)
    return run_dir.parent.parent if run_dir.parent.name == "creator-runs" else run_dir.parent


def build_creator_prompt(run_dir, run_doc, project_manifest, instructions_index, *, prompt_type="initial_onboarding", context=None):
    """Build the versioned Creator prompt from run inputs (§4.5).

    Supports the five normative scenarios:
    - initial_onboarding (incorporación inicial)
    - material_change_regeneration (regeneración por cambio material)
    - framework_update (actualización de framework/DSH)
    - repair_retained (corrección de generación RETAINED)
    - skill_lifecycle (creación/mejora de skills específicas)
    """
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"Tipo de prompt no válido: {prompt_type}; permitidos: {PROMPT_TYPES}")

    gen_id = run_doc["generation_id"]
    project_name = run_doc["project"]["name"]
    framework_rev = run_doc.get("framework_revision", "unknown")
    workspace = _run_workspace(run_dir)
    base_rev = project_manifest.get("base_revision", "unknown")

    header = f"""# Creator Generation Request — {project_name}

**Generation ID:** {gen_id}
**Prompt version:** {PROMPT_VERSION}
**Scenario:** {prompt_type}
**Framework revision:** {framework_rev}
**Project:** {project_name}
**Base revision:** {base_rev}
"""

    if prompt_type == "initial_onboarding":
        objective = f"""## Objetivo

Genera un paquete completo y específico para el proyecto `{project_name}`.
El paquete debe incluir exactamente dos modos finales:
- `{project_name}-auditor`
- `{project_name}-continuous-repair`

Más skills específicas justificadas con procedimiento recurrente, evidencia,
fronteras y prueba."""

    elif prompt_type == "material_change_regeneration":
        objective = f"""## Objetivo — Regeneración por cambio material

El proyecto `{project_name}` ha registrado un cambio material de base.
Compara la base previa con la actual, detecta drift con `drift-analyzer (sync)`,
conserva las decisiones previas aprobadas y regenera únicamente los modos, contratos
y skills afectados por el cambio."""

    elif prompt_type == "framework_update":
        objective = f"""## Objetivo — Actualización de framework/DSH

El framework o runtime DSH se ha actualizado a `{framework_rev}`.
Actualiza los adaptadores y schemas manteniendo intactos los procedimientos,
fronteras y contratos específicos del proyecto `{project_name}`."""

    elif prompt_type == "repair_retained":
        reason = (context or {}).get("reason", "Hallazgos retenidos en validación previa")
        objective = f"""## Objetivo — Corrección de generación RETAINED

La generación previa fue marcada RETAINED por el Host.
Causa reportada: {reason}.
Usa `generation-repair (debug)` para corregir los artefactos afectados dentro de los límites
autorizados. No modifiques validadores, tests ni holdouts."""

    elif prompt_type == "skill_lifecycle":
        skill_name = (context or {}).get("skill_name", "skill-especifica")
        objective = f"""## Objetivo — Ciclo de vida de skill específica

Diseña o mejora la skill `{skill_name}` para `{project_name}`.
Requisitos obligatorios: procedimiento recurrente, evidencia observable en el proyecto,
fronteras estrictas de lectura/escritura y prueba ejecutable."""

    library_section = _library_selection_section()
    import generation_contracts as gc
    scenario_types = ", ".join(f"`{value}`" for value in sorted(gc.SCENARIO_TYPES))
    scenario_verdicts = ", ".join(
        f"`{value}`" for value in sorted(gc.SCENARIO_VERDICTS))
    holdout_families = ", ".join(
        f"`{value}`" for value in sorted(gc.HOLDOUT_FAMILIES))
    body = f"""
## Estrategia de selección obligatoria

Resuelve cada necesidad en este orden estricto:
1. `base-library` — biblioteca base inmutable
2. `specialized-catalog` — catálogo de patrones especializados
3. `composition` — composición de varias skills
4. `override` — override declarativo limitado
5. `extension` — extensión específica generada (requiere justificación de por qué no aplican las capas anteriores)
6. `RETAINED` si ninguna opción es aceptable

{library_section}

## Pipeline interno

Ejecuta las capacidades internas en orden:
- project-discovery (audit): descubrir proyecto
- project-documenter (document): normalizar instrucciones
- contract-risk-mapper (audit + architect): mapear contratos y riesgos
- capability-partitioner (scope): particionar capacidades
- capability-designer (architect): diseñar modos y skills
- scenario-author (test): crear escenarios
- skill-generator (develop): generar skills
- generation-repair (debug): reparar si necesario
- drift-analyzer (sync): analizar drift si aplica

## Salida obligatoria

Escribe bajo `{run_dir}/generated/`:
- `generation-manifest.json` (status: GENERATED, con schema_version, generation_id, status, project: {{name, root_identity, base_revision}}, creator: {{session_ref, runtime_version}}, framework: {{revision}}, artifacts: [{{path, type, sha256}}], required_capabilities, forbidden_capabilities, effective_routing_digest, context_policy: {{skill_entrypoint_max_bytes, support_file_max_bytes, warning_ratio}}, license_provenance)
- `project-manifest.json`
- `capabilities.json`
- `modes/{project_name}-auditor/`
- `modes/{project_name}-continuous-repair/`
- `skills/` (skills justificadas)
- `contracts/`
- `acceptance-plan.json`
- `generation-report.md`

## Contratos exactos de salida (sin formas ad hoc)

Los schemas normativos están en `{FRAMEWORK}/schemas/`; en particular, valida
`acceptance-plan.json` contra `{FRAMEWORK}/schemas/acceptance-plan.schema.json`.
Su forma mínima exacta es:
```json
{{
  "schema_version": 1,
  "generation_id": "{gen_id}",
  "requirements": [{{"id": "SR-1", "criterion": "...", "evidence": "..."}}],
  "public_scenarios": [{{"id": "PUBLIC-1", "type": "positive", "target": "{project_name}-auditor", "expected": "PASS"}}],
  "holdout_families": ["prompt-injection-in-repository"],
  "gates": ["public scenarios", "hidden holdouts", "independent review"],
  "creator_limit": "Host validation only; no ACTIVE authority."
}}
```
Campos opcionales únicamente: `status` (solo `GENERATED`) y
`candidate_base_revision` (string no vacío). Cada requirement contiene
exactamente `id,criterion,evidence`; cada public scenario contiene exactamente
`id,type,target,expected`. Enums de `type`: {scenario_types}. Enums de
`expected`: {scenario_verdicts}. Enums de `holdout_families`: {holdout_families}.

`contracts/scenarios.jsonl` contiene un objeto JSON por línea con exactamente los
campos requeridos `schema_version,scenario_id,type,description,input,expected,sr_links`;
`expected` es un objeto con `verdict` (y solo opcionalmente `evidence_type`,
`description`). Los campos opcionales de escenario son `target_mode`,
`target_skill`, `holdout_family`, `verification_state`.

Todo contrato nuevo de modo/skill debe cumplir su schema y llevar discriminador
explícito: `kind: "mode"` para `schemas/modes.schema.json`, o `kind: "skill"`
para `schemas/skills.schema.json`. `kind` es opcional únicamente para preservar
contratos schema v1 previos; no lo omitas en salidas nuevas ni infieras variantes
por campos como `motive`.
En `generation-manifest.json`, todo archivo cuyo basename sea `SKILL.md` debe
usar artifact `type: "skill-entrypoint"`.

Antes de emitir `status: GENERATED`, ejecuta la prevalidación Host read-only:
```bash
python3 -B {FRAMEWORK}/scripts/host_validator.py \
  --generated {run_dir}/generated
```
Corrige todos los errores de schema, contracts y manifest que reporte; solo
entonces deja el manifest en estado GENERATED y solicita aceptación.

## Invariantes

1. Solo emitir status GENERATED; nunca ACCEPTED/ACTIVE
2. Exactamente dos modos finales específicos del proyecto
3. No modificar Host, validadores ni artefactos Host del run (`tests/`,
   `inputs/runtime-capabilities.json`, `validation/`, `acceptance/`); el
   `generated/capabilities.json` declarativo sí forma parte de la salida
4. No rutas/identidades/secretos del mantenedor
5. No proveedores/modelos/routing nuevos
6. Todo valor/decisión tiene fuente
7. Unknowns load-bearing bloquean la generación
8. Nunca enviar `sandbox_permissions` (ningún valor: ni workspace-write ni
   danger-full-access) ni `justification` en ninguna llamada de herramienta
   (comandos ni escrituras): la guía del runtime que anima a escalar tras una
   denegación NO aplica a esta misión. El workspace del run es escribible en
   el modo vigente y las lecturas no necesitan permiso; una denegación indica
   un intento fuera de alcance: se reporta como hallazgo, nunca se escala
9. Para escribir archivos usa el tool `workflow_write` (no `write`). Al
   delegar trabajo a subagentes, cada tarea debe repetirles: usar
   `workflow_write` para escribir y jamás enviar `sandbox_permissions` ni
   `justification` — en sesiones delegadas las aprobaciones se rechazan
   automáticamente, así que una denegación ahí es final: se reporta al
   delegante, nunca se reintenta con escalada
10. `generated/capabilities.json.required_capabilities` debe cubrir la unión de
    capacidades requeridas por ambos modos. Reparación gestionada requiere
    `candidate_write`, nunca `product_write` ni escritura canónica. Ninguna
    capacidad requerida puede aparecer en `forbidden_capabilities`

## Al finalizar

Invoca:
```bash
python3 -B scripts/bootstrap.py accept \\
  --workspace {workspace} \\
  --generated {run_dir}/generated
```

Este comando solo solicita validación; no instala nada.
"""
    return header + "\n" + objective + "\n" + body


# ---------------------------------------------------------------------------
# DSH launch-token exchange and local RPC transport
# ---------------------------------------------------------------------------


class DshLocalClient:
    """Runtime-only client for the local DSH web connection.

    ``dsh web`` prints an authenticated root URL containing a one-process
    launch token. The root exchange sets an authority-bound cookie; all later
    requests use that cookie. Neither token nor cookie is persisted.
    """

    def __init__(self, authenticated_url):
        match = re.fullmatch(r"(https?://[^/?#]+)(?:/[^?#]*)?\?token=([^&#]+)", authenticated_url)
        if not match:
            raise ValueError("DSH authenticated URL has no launch token")
        self.base_url = match.group(1)
        self._token_url = authenticated_url
        self._cookie = None

    @classmethod
    def from_console_line(cls, line):
        match = _DSH_URL_RE.search(line)
        if not match:
            raise ValueError("No dsh web authenticated URL in console output")
        return cls(match.group(1))

    @classmethod
    def from_dsh_home(cls, dsh_home, port=3080):
        """Authenticate using local .credentials.yaml HMAC-SHA256 browser secret."""
        cred_path = Path(dsh_home) / ".credentials.yaml"
        if not cred_path.is_file():
            raise ValueError(f"No .credentials.yaml at {dsh_home}")
        content = cred_path.read_text(encoding="utf-8")
        m = re.search(r"secret:\s*([A-Za-z0-9_-]+)", content)
        if not m:
            raise ValueError("No browser-session secret in .credentials.yaml")
        raw_secret = m.group(1)
        pad = "=" * ((4 - len(raw_secret) % 4) % 4)
        secret = base64.urlsafe_b64decode(raw_secret + pad)
        authority = f"127.0.0.1:{port}"

        def b64url(b):
            return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

        auth_hash = hashlib.sha256(authority.encode("utf-8")).digest()
        cookie_name = "dsh-auth-" + b64url(auth_hash)
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + 30 * 24 * 3600 * 1000
        payload = json.dumps({
            "version": 1,
            "authority": authority,
            "issuedAt": now_ms,
            "expiresAt": expires_ms,
        }, separators=(",", ":")).encode("utf-8")
        body = b64url(payload)
        sig = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).digest()

        instance = cls.__new__(cls)
        instance.base_url = f"http://{authority}"
        instance._token_url = None
        instance._cookie = f"{cookie_name}=v1.{body}.{b64url(sig)}"
        return instance

    @property
    def authenticated(self):
        return self._cookie is not None

    def exchange_token(self, timeout=10):
        request = urllib.request.Request(self._token_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                cookie = response.headers.get("Set-Cookie")
                if not cookie:
                    raise ValueError("DSH token exchange returned no session cookie")
                self._cookie = cookie.split(";", 1)[0]
                return response.geturl()
        except urllib.error.HTTPError as exc:
            raise ValueError(f"DSH token exchange failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"DSH connection failed: {exc.reason}") from exc

    def request_json(self, path, *, method="GET", payload=None, timeout=30):
        if not self.authenticated:
            raise ValueError("DSH client is not authenticated")
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Cookie": self._cookie, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"DSH request failed: HTTP {exc.code}") from exc

    def rpc(self, endpoint, args=None, timeout=30):
        """Call one generated DSH Remote unary endpoint through ``/api``."""
        result = self.request_json(
            "/api/" + endpoint, method="POST",
            payload={
                "type": "client-request",
                "rpcId": secrets.token_hex(12),
                "method": endpoint,
                "payload": {"args": args or {}},
            },
            timeout=timeout,
        )
        inner = result.get("result", result) if isinstance(result, dict) else result
        if isinstance(inner, dict) and inner.get("ok") is False:
            raise ValueError(f"DSH RPC {endpoint} rejected: {inner}")
        return inner

    def list_sessions(self):
        """Return the Host session list through the generated descriptor."""
        return self.rpc("session/list", {"_request": {}})

    def create_workspace(self, path):
        """Register (or look up) ``path`` in the workspace registry.

        Idempotent: a known path returns its existing workspaceId with
        ``created: false``. Sessions the UI groups under a workspace name are
        the ones attached here; a session created without this attachment
        shows as ungrouped.
        """
        created = self.rpc("workspace/create", {"request": {"path": str(path)}})
        value = created.get("value", created) if isinstance(created, dict) else created
        workspace = value.get("workspace") if isinstance(value, dict) else None
        workspace_id = workspace.get("workspaceId") if isinstance(workspace, dict) else None
        if not workspace_id:
            raise ValueError("DSH workspace/create returned no workspaceId")
        return workspace_id

    def create_creator_session(self, *, workspace_path, agent_preset="cordis",
                               session_id=None):
        """Create the Creator session bound to the run's workspace.

        session/create accepts workspaceId or cwd, not both. With a
        workspaceId DSH attaches the session to the workspace registry and
        uses the workspace path as the session cwd — which is the
        workspace-write boundary. A bare cwd leaves the session unattached
        (ungrouped in the UI) and confines writes to the run directory alone,
        so any workspace-level write is denied and drifts into escalation
        requests.
        """
        workspace_id = self.create_workspace(workspace_path)
        req = {"workspaceId": workspace_id}
        if agent_preset:
            req["agentPreset"] = agent_preset
        if session_id:
            req["sessionId"] = session_id
        created = self.rpc("session/create", {"request": req})
        value = created.get("value", created) if isinstance(created, dict) else created
        session_id = value.get("sessionId") if isinstance(value, dict) else None
        if not session_id:
            raise ValueError("DSH session/create returned no sessionId")
        return session_id

    def send_prompt(self, session_id, prompt, *, request_id=None):
        """Queue a text prompt under a stable, Host-owned request identity."""
        return self.rpc("session/prompt", {"request": {
            "requestId": request_id or secrets.token_hex(16),
            "sessionId": session_id,
            "mode": "queue",
            "content": [{"type": "text", "text": prompt}],
        }})

    def cancel_session(self, session_id):
        """Request cancellation of the active turn without dropping its inbox."""
        return self.rpc("session/cancel", {"request": {"sessionId": session_id}})

    def session_page(self, session_id, *, through_seq, before_seq=None,
                     max_messages=200):
        """Read a durable, message-aligned page from the real DSH journal."""
        request = {
            "address": {"kind": "session", "sessionId": session_id},
            "throughSeq": through_seq,
            "maxMessages": max_messages,
        }
        if before_seq is not None:
            request["beforeSeq"] = before_seq
        return self.rpc("session/page", {"request": request})

    def stream_snapshot(self, session_id, *, timeout=10):
        """Open real ``session/follow`` and ``session/control`` mux streams.

        The helper takes one opening baseline from each stream over the
        authenticated ``/api/remote.mux`` WebSocket. Those opening frames are
        authoritative: follow supplies the durable cursor/log and control
        supplies live queues/jobs. No list-summary cursor is synthesized.
        """
        helper = Path(__file__).resolve().parent / "dsh_stream_snapshot.mjs"
        payload = json.dumps({
            "baseUrl": self.base_url,
            "cookie": self._cookie,
            "sessionId": session_id,
            "timeoutMs": int(timeout * 1000),
        })
        try:
            result = subprocess.run(
                ["node", str(helper)], input=payload, capture_output=True,
                text=True, timeout=timeout + 5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"DSH Remote stream helper falló: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or "sin diagnóstico"
            raise ValueError(f"DSH Remote stream rechazado: {detail}")
        try:
            snapshot = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("DSH Remote stream devolvió JSON inválido") from exc
        if not isinstance(snapshot.get("follow"), dict) or not isinstance(
                snapshot.get("control"), dict):
            raise ValueError("DSH Remote stream no devolvió ambos baselines")
        return snapshot

    def creator_observation(self, session_id, *, cursor=-1):
        """Return authoritative durable and live state for Creator supervision."""
        snapshot = self.stream_snapshot(session_id)
        follow = snapshot["follow"]
        control = snapshot["control"]
        observed_cursor = follow.get("cursor")
        if not isinstance(observed_cursor, int):
            raise ValueError("session/follow snapshot sin cursor durable")
        records = list(follow.get("records") or [])
        has_more = bool(follow.get("hasMore"))
        before_seq = min(
            (record["event"]["seq"] for record in records
             if isinstance(record, dict) and record.get("type") == "event"
             and isinstance(record.get("event"), dict)
             and isinstance(record["event"].get("seq"), int)),
            default=observed_cursor + 1)
        pages = 0
        while has_more and cursor < before_seq - 1:
            pages += 1
            if pages > 100:
                raise ValueError("session/page excedió el límite de supervisión")
            page = self.session_page(
                session_id, through_seq=observed_cursor,
                before_seq=before_seq, max_messages=200)
            value = page.get("value", page) if isinstance(page, dict) else page
            older = value.get("records", []) if isinstance(value, dict) else []
            if not older:
                raise ValueError("session/page indicó hasMore sin registros")
            records = list(older) + records
            prior = before_seq
            before_seq = min(
                (record["event"]["seq"] for record in older
                 if isinstance(record, dict) and record.get("type") == "event"
                 and isinstance(record.get("event"), dict)
                 and isinstance(record["event"].get("seq"), int)),
                default=before_seq)
            if before_seq >= prior:
                raise ValueError("session/page no avanzó el cursor histórico")
            has_more = bool(value.get("hasMore"))
        events = [record.get("event") for record in records
                  if isinstance(record, dict) and record.get("type") == "event"
                  and isinstance(record.get("event"), dict)
                  and record["event"].get("seq", -1) > cursor]

        listed = self.list_sessions()
        value = listed.get("value", listed) if isinstance(listed, dict) else listed
        items = value.get("items", []) if isinstance(value, dict) else []
        target = next((item for item in items
                       if item.get("sessionId") == session_id), None)
        if target is None:
            raise ValueError(f"DSH session {session_id} no aparece en session/list")
        by_parent = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            parent_id = item.get("parentSessionId")
            if parent_id:
                by_parent.setdefault(parent_id, []).append(item)
        descendants = []
        pending = [session_id]
        reached_ids = {session_id}
        while pending:
            parent_id = pending.pop()
            for child in by_parent.get(parent_id, []):
                child_id = child.get("sessionId")
                if not child_id or child_id in reached_ids:
                    continue
                reached_ids.add(child_id)
                descendants.append(child)
                pending.append(child_id)

        jobs_by_session = control.get("jobs") or {}
        if not isinstance(jobs_by_session, dict):
            raise ValueError("session/control baseline sin mapa jobs")
        jobs = []
        for reached_id in reached_ids:
            session_jobs = jobs_by_session.get(reached_id, [])
            if not isinstance(session_jobs, list):
                raise ValueError(
                    f"session/control jobs inválidos para {reached_id}")
            jobs.extend({**job, "sessionId": reached_id}
                        for job in session_jobs if isinstance(job, dict))
        return {
            "cursor": observed_cursor,
            "events": events,
            "running": bool(target.get("running")),
            "descendants": descendants,
            "jobs": jobs,
        }


class CreatorSession:
    """Manages a Creator generation session.

    In production, this would use the DSH RPC/API. For C2 implementation,
    this provides the structural contract and supervision framework.
    """

    def __init__(self, run_dir, *, timeout_seconds=1800, max_tokens=500000):
        self.run_dir = Path(run_dir)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.start_time = None
        self.token_count = 0
        self.status = "IDLE"
        self._session_ref = None

    def validate_preconditions(self):
        """Verify run directory is properly set up for Creator."""
        if not self.run_dir.is_dir():
            raise ValueError(f"Run directory no existe: {self.run_dir}")

        run_json = self.run_dir / "run.json"
        if not run_json.is_file():
            raise ValueError("run.json no encontrado")

        run_doc = _read_json(run_json)
        if run_doc.get("status") not in ("CREATED", "GENERATING"):
            raise ValueError(
                f"Run en estado inesperado: {run_doc.get('status')}; "
                "debe ser CREATED o GENERATING"
            )

        # Check inputs exist
        required_inputs = [
            "bootstrap-request.json", "snapshot.json", "inventory.json",
            "authority.json", "host-policy.json", "effective-routing.json",
            "runtime-capabilities.json",
        ]
        for name in required_inputs:
            if not (self.run_dir / "inputs" / name).is_file():
                raise ValueError(f"Input faltante: {name}")

        # Check discovery exists
        for name in ("instructions-index.json", "project-manifest.json"):
            if not (self.run_dir / "discovery" / name).is_file():
                raise ValueError(f"Discovery faltante: {name}")

        return run_doc

    def prepare(self):
        """Prepare the Creator session: build prompt and update status."""
        run_doc = self.validate_preconditions()
        gen_id = run_doc["generation_id"]

        # Load project manifest and instructions
        project_manifest = _read_json(
            self.run_dir / "discovery" / "project-manifest.json"
        )
        instructions_index = _read_json(
            self.run_dir / "discovery" / "instructions-index.json"
        )

        # Build prompt
        prompt = build_creator_prompt(
            self.run_dir, run_doc, project_manifest, instructions_index
        )

        # Save prompt
        prompt_path = self.run_dir / "creator-prompt.md"
        if not prompt_path.exists():
            prompt_path.write_text(prompt, encoding="utf-8")

        # Save generation request
        request_path = self.run_dir / "generation-request.json"
        if not request_path.exists():
            _write_json(request_path, {
                "schema_version": SCHEMA_VERSION,
                "generation_id": gen_id,
                "prompt_version": PROMPT_VERSION,
                "prompt_digest": _digest_bytes(prompt.encode("utf-8")),
                "project_name": run_doc["project"]["name"],
                "skill_selection_order": SKILL_SELECTION_ORDER,
                "internal_capabilities": CREATOR_INTERNAL_CAPABILITIES,
                "budget": run_doc.get("budget", {}),
                "timestamp": _now_iso(),
            })

        # Update run status to GENERATING
        run_doc["status"] = "GENERATING"
        run_doc["updated_at"] = _now_iso()
        _update_json(self.run_dir / "run.json", run_doc)

        # Update checkpoint
        _update_json(self.run_dir / "checkpoint.json", {
            "schema_version": SCHEMA_VERSION,
            "generation_id": gen_id,
            "phase": "GENERATING",
            "completed_phases": [
                "preflight", "snapshot", "inventory", "skills",
                "prompt_build",
            ],
            "pending_phases": ["creator_call", "generation", "accept"],
            "timestamp": _now_iso(),
            "resumable": True,
        })

        self.status = "PREPARED"
        return {
            "generation_id": gen_id,
            "prompt_digest": _digest_bytes(prompt.encode("utf-8")),
            "prompt_path": str(prompt_path),
        }

    def check_budget(self, *, now=None):
        """Check the limits frozen in ``run.json`` for this invocation."""
        if self.start_time is None:
            return True
        now = time.time() if now is None else now
        elapsed = now - self.start_time
        if elapsed > self.timeout_seconds:
            raise ValueError(
                f"Timeout: {elapsed:.0f}s excede {self.timeout_seconds}s"
            )
        if self.token_count > self.max_tokens:
            raise ValueError(
                f"Token budget excedido: {self.token_count} > {self.max_tokens}"
            )
        return True

    def verify_generation_output(self):
        """Verify Creator produced required outputs.

        Checks that generated/ contains the required artifacts.
        Does NOT validate content (that's C3's job).
        """
        gen_dir = self.run_dir / "generated"
        if not gen_dir.is_dir():
            raise ValueError("generated/ no existe")

        # Required files
        manifest_path = gen_dir / "generation-manifest.json"
        if not manifest_path.is_file():
            raise ValueError("generation-manifest.json faltante")
        if manifest_path.is_symlink():
            raise ValueError("generation-manifest.json es enlace simbólico")

        manifest = _read_json(manifest_path)

        # Status must be GENERATED
        if manifest.get("status") != "GENERATED":
            raise ValueError(
                f"Creator emitió status {manifest.get('status')!r}; "
                "debe ser GENERATED"
            )

        # Must have artifacts
        if not manifest.get("artifacts"):
            raise ValueError("Manifest sin artefactos")

        # Check Creator only wrote inside staging (generated/)
        for art in manifest["artifacts"]:
            path = art.get("path", "")
            if path.startswith("/") or ".." in path:
                raise ValueError(
                    f"Artefacto con ruta fuera de staging: {path}"
                )

        # Check no self-acceptance
        for art in manifest["artifacts"]:
            if art.get("path", "").endswith("host-verdict.json"):
                raise ValueError(
                    "Creator intentó escribir host-verdict.json (auto-aprobación)"
                )

        # Host-owned read-only prevalidation must pass before create_finish()
        # advances run.json/checkpoint.json to GENERATED.
        import host_validator
        report = host_validator.validate_package(gen_dir, run_dir=self.run_dir)
        if not report.passed:
            failures = []
            for layer, result in report.layers.items():
                if not result["passed"]:
                    detail = "; ".join(result["details"]) or "sin detalle"
                    failures.append(f"{layer}: {detail}")
            raise HostPrevalidationFailed(
                "Prevalidación Host falló antes de GENERATED: "
                + " | ".join(failures))

        return manifest

    def create_finish(self, manifest):
        """Create finish.json to mark generation complete."""
        gen_id = manifest.get("generation_id", "unknown")
        finish_path = self.run_dir / "finish.json"
        if not finish_path.exists():
            _write_json(finish_path, {
                "schema_version": SCHEMA_VERSION,
                "generation_id": gen_id,
                "status": "GENERATED",
                "artifact_count": len(manifest.get("artifacts", [])),
                "manifest_digest": _digest_bytes(
                    json.dumps(manifest, sort_keys=True).encode("utf-8")
                ),
                "timestamp": _now_iso(),
            })

        # Update run status
        run_doc = _read_json(self.run_dir / "run.json")
        run_doc["status"] = "GENERATED"
        run_doc["updated_at"] = _now_iso()
        _update_json(self.run_dir / "run.json", run_doc)

        # Update checkpoint
        _update_json(self.run_dir / "checkpoint.json", {
            "schema_version": SCHEMA_VERSION,
            "generation_id": gen_id,
            "phase": "GENERATED",
            "completed_phases": [
                "preflight", "snapshot", "inventory", "skills",
                "prompt_build", "creator_call", "generation",
            ],
            "pending_phases": ["accept"],
            "timestamp": _now_iso(),
            "resumable": True,
        })

        return {
            "result": "GENERATED",
            "generation_id": gen_id,
            "artifact_count": len(manifest.get("artifacts", [])),
        }

    def retain(self, reason):
        """Mark the generation as RETAINED with a reason."""
        run_doc = _read_json(self.run_dir / "run.json")
        gen_id = run_doc.get("generation_id", "unknown")
        run_doc["status"] = "RETAINED"
        run_doc["updated_at"] = _now_iso()
        _update_json(self.run_dir / "run.json", run_doc)

        _update_json(self.run_dir / "checkpoint.json", {
            "schema_version": SCHEMA_VERSION,
            "generation_id": gen_id,
            "phase": "RETAINED",
            "reason": reason,
            "completed_phases": [],
            "pending_phases": [],
            "timestamp": _now_iso(),
            "resumable": False,
        })

        return {
            "result": "RETAINED",
            "generation_id": gen_id,
            "reason": reason,
        }


DSH_PLUGIN_PATCH = Path(__file__).resolve().parent / "dsh-plugins" / "cordis-patch.yml"


def _patched_launch_command(command):
    """Append ``--patch`` to the launch argv when the plugin overlay exists.

    The overlay loads ``workflow-write.mjs`` (same-mode ``sandbox_permissions``
    is not an escalation), fixing the upstream write rejection observed in the
    pilot. DSH fails loud when a named overlay cannot apply, so the file must
    exist; DSH_PLUGIN_PATCH=0 launches without it for escapes.
    """
    if os.environ.get("DSH_PLUGIN_PATCH") == "0":
        return list(command)
    if not DSH_PLUGIN_PATCH.is_file():
        return list(command)
    return [*command, "--patch", str(DSH_PLUGIN_PATCH)]


def _terminate_process(process, *, wait_timeout=5):
    """Kill, reap, and close captured output for a failed launch."""
    try:
        process.kill()
    except OSError:
        pass
    wait = getattr(process, "wait", None)
    if wait is not None:
        try:
            wait(timeout=wait_timeout)
        except (OSError, subprocess.TimeoutExpired):
            pass
    stdout = getattr(process, "stdout", None)
    if stdout is not None:
        try:
            stdout.close()
        except OSError:
            pass


def launch_dsh_web(command=("npx", "-y", "@deepseek-ai/dsh", "web"), *,
                   env=None, spawn_timeout=120):
    """Launch DSH web and return ``(process, client)`` after token capture.

    ``-y`` keeps npx non-interactive (an "Ok to proceed?" prompt aborts
    without a TTY); stdin is null. The child remains attached for the
    caller's authenticated session. Output is consumed in memory; no
    token-bearing line is written to disk. When DSH exits without a URL,
    the captured output is included in the error with any token redacted,
    so the launch failure is diagnosable.
    """
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    process = subprocess.Popen(
        _patched_launch_command(command), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
        bufsize=1, env=child_env,
    )
    captured = []
    deadline = time.monotonic() + spawn_timeout
    url_line = None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while time.monotonic() < deadline:
            remaining = max(0, deadline - time.monotonic())
            ready = selector.select(min(remaining, 0.25))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            captured.append(line.rstrip())
            if "dsh web:" in line and "?token=" in line:
                url_line = line
                break
    finally:
        selector.close()
    if url_line:
        return process, DshLocalClient.from_console_line(url_line)
    exit_before_kill = process.poll()
    _terminate_process(process)
    tail = re.sub(r"\?token=\S+", "?token=<redacted>",
                  "\n".join(captured[-15:])) or "<sin salida>"
    raise RuntimeError(
        "DSH no imprimió una URL autenticada (exit="
        f"{exit_before_kill}); salida capturada sin token:\n{tail}")


# ---------------------------------------------------------------------------
# Orchestration: run the full Creator pipeline
# ---------------------------------------------------------------------------


DSH_HOME_CANDIDATES = ("~/.dsh", "~/.deepseek", "~/.config/dsh")


def _read_settings_structure(dsh_home):
    """Parse settings.yaml into the fields the provider check needs.

    Structure only: provider names, apiKeyEnv NAMES and model counts.
    API key values are never read, stored or logged.
    """
    path = Path(dsh_home) / "settings.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()

    def block_after(header_regex):
        for i, line in enumerate(lines):
            m = re.match(header_regex, line)
            if m:
                base_indent = len(m.group(1))
                out = []
                for child in lines[i + 1:]:
                    if not child.strip() or child.lstrip().startswith("#"):
                        continue
                    if len(child) - len(child.lstrip()) <= base_indent:
                        break
                    out.append(child)
                return out
        return None

    default = {}
    blk = block_after(r"^(\s*)agent-default-model:\s*$")
    if blk:
        for child in blk:
            m = re.match(r"^\s*(provider|model):\s*(\S.*)$", child)
            if m:
                default[m.group(1)] = m.group(2).strip().strip('"\'')
    if "provider" in default:
        default["provider"] = default["provider"].strip().strip('"\'')

    providers = {}
    blk = block_after(r"^(\s*)providers:\s*$")
    if blk:
        prov_indent = min(len(c) - len(c.lstrip()) for c in blk)
        current = None
        for child in blk:
            indent = len(child) - len(child.lstrip())
            m = re.match(r"^\s*([A-Za-z0-9_-]+):\s*(.*)$", child)
            if m and indent == prov_indent:
                if m.group(2) == "":
                    current = m.group(1)
                    providers.setdefault(
                        current,
                        {"api_key_env": None, "models": 0, "first_model": None})
                else:
                    current = None
                continue
            if not current:
                continue
            km = re.match(r"^\s*([A-Za-z0-9_-]+):\s*(\S.*)$", child)
            if km and km.group(1) == "apiKeyEnv":
                providers[current]["api_key_env"] = (
                    km.group(2).strip().strip('"\''))
            m_id = re.match(r"^\s*-\s+id\s*:\s*(\S.*)$", child)
            if m_id:
                providers[current]["models"] += 1
                if not providers[current]["first_model"]:
                    providers[current]["first_model"] = (
                        m_id.group(1).strip().strip('"\''))
    return default, providers


def _find_dsh_pids():
    """PIDs of running DSH web processes (exact command match)."""
    try:
        result = subprocess.run(
            ["pgrep", "-af", "dsh"], capture_output=True, text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid, cmdline = int(parts[0]), parts[1]
        if pid == os.getpid():
            continue
        if _is_dsh_web_cmdline(cmdline):
            pids.append(pid)
    return pids


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_dsh_web_cmdline(cmdline):
    """Whether a command line is a DSH web instance.

    Covers both registry paths (@deepseek-ai/dsh) and npx bin symlinks
    (node_modules/.bin/dsh), which carry no scope in their path. A web
    indicator is required so other dsh-named tools never match.
    """
    if not cmdline:
        return False
    tokens = cmdline.split()
    has_dsh_bin = any(os.path.basename(token) == "dsh" for token in tokens)
    has_web = " web" in cmdline or "--profile web" in cmdline
    return ("@deepseek-ai/dsh" in cmdline or has_dsh_bin) and has_web


def _cmdline_of(pid):
    """Command line of a PID from /proc (spaces joined), or empty string."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def _port_listener_pid(port):
    """(pid, raw line) of whatever LISTENs on the TCP port, via ss.

    Returns ``(None, "")`` when the port is free or ss is unavailable.
    """
    try:
        result = subprocess.run(
            ["ss", "-tlnp"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    for line in result.stdout.splitlines():
        if re.search(r":%d\b" % port, line) and "pid=" in line:
            m = re.search(r"pid=(\d+)", line)
            if m:
                return int(m.group(1)), line.strip()
    return None, ""


def _ensure_port_free_for_dsh(port=3080, timeout=6):
    """Clear the DSH web port: stop lingering DSH listeners, refuse foreign ones.

    A listener whose command line belongs to DSH is stopped and the port is
    re-checked until the deadline. A foreign listener is never killed: the
    check fails naming its PID and command so the holder can decide.
    Returns ``None`` when the port is free, otherwise the failure reason.
    """
    deadline = time.time() + timeout
    while True:
        pid, _line = _port_listener_pid(port)
        if pid is None:
            return None
        cmdline = _cmdline_of(pid)
        if not _is_dsh_web_cmdline(cmdline):
            return (f"puerto {port} ocupado por un proceso ajeno a DSH "
                    f"(PID {pid}: {cmdline[:90] or 'sin cmdline'}); "
                    "libéralo y vuelve a intentarlo")
        if time.time() >= deadline:
            return (f"la instancia DSH con PID {pid} no liberó el puerto "
                    f"{port} en {timeout}s")
        _stop_dsh_instances([pid])
        time.sleep(0.3)


def _stop_dsh_instances(pids, *, timeout=10):
    """Terminate DSH web processes: SIGTERM, wait, SIGKILL fallback.

    Returns the list of PIDs that were signaled (evidence for the run).
    """
    import signal
    stopped = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except OSError:
            continue
    deadline = time.time() + timeout
    while time.time() < deadline and any(_pid_alive(p) for p in stopped):
        time.sleep(0.2)
    for pid in stopped:
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return stopped


def _env_var_present(name):
    """Whether an env var is set and non-empty, without keeping its value.

    A running DSH may hold the key in its own process environment; those
    environments are inspected for the variable NAME only and any value
    found is discarded immediately.
    """
    if os.environ.get(name):
        return True
    for pid in _find_dsh_pids():
        try:
            raw = Path(f"/proc/{pid}/environ").read_bytes()
        except OSError:
            continue
        prefix = name.encode() + b"="
        for part in raw.split(b"\0"):
            if part.startswith(prefix) and part[len(prefix):].strip():
                return True
    return False


def dsh_provider_status(dsh_home):
    """Resolve a usable provider/model without assuming one setup.

    No user can be expected to hold the same provider keys: the resolver
    walks the providers configured in settings.yaml — DSH's own default
    (the last model the user configured) first, then the rest in
    configuration order — and picks the first one that has models and
    whose key variable is present. Variable NAMES only; values are never
    read, copied or logged. When nothing is usable it stops with the
    per-provider missing variable so the run keeps a single actionable
    message.
    """
    home = Path(dsh_home).expanduser()
    try:
        default, providers = _read_settings_structure(home)
    except (OSError, ValueError) as e:
        return {"ok": False,
                "reason": f"settings.yaml no legible en {home}: {e}"}
    if not providers:
        return {"ok": False,
                "reason": f"settings.yaml en {home} no declara providers"}
    preferred = default.get("provider")
    ordered = list(providers)
    if preferred in providers:
        ordered.remove(preferred)
        ordered.insert(0, preferred)
    checked = []
    for name in ordered:
        info = providers[name]
        if info["models"] == 0:
            checked.append(f"{name}: sin modelos")
            continue
        env_name = info["api_key_env"]
        if env_name and not _env_var_present(env_name):
            checked.append(f"{name}: llave {env_name} ausente")
            continue
        return {"ok": True, "provider": name, "models": info["models"],
                "model": info["first_model"], "api_key_env": env_name,
                "source": ("default" if name == preferred else "fallback"),
                "skipped": checked}
    detail = "; ".join(checked) or "sin proveedores con modelos"
    return {"ok": False,
            "reason": "ningún proveedor utilizable (" + detail +
                      "); define la llave de alguno en el entorno de DSH "
                      "y vuelve a intentarlo"}


def _provider_gate_origin(status, origin=None):
    """Origin string for the acquisition result.

    Keys visible in the process environment are only one of DSH's possible
    sources (dotenv, keychain, UI-entered credentials): a missing key is a
    warning, not a block — the real authentication failure would surface as
    a retained run with its cause. DSH_PROVIDER_STRICT handling (the hard
    stop) belongs to the caller.
    """
    if status["ok"]:
        base = origin or "launched:dsh-web"
        return f"{base} ({status['provider']})"
    return ("aviso: " + status["reason"] + (
        "; se despacha igualmente: DSH puede resolver la llave por otros "
        "medios (dotenv/keychain/UI). Si Creator falla por autenticación "
        "el run quedará RETAINED con la causa"))


def _provider_home(candidates):
    """First candidate home that actually holds a settings.yaml."""
    for home in candidates:
        if (Path(home) / "settings.yaml").is_file():
            return home
    return None


def acquire_dsh_client(*, launch=False):
    """Acquire an authenticated, provider-ready DSH client.

    Order: injected client (caller), env DSH_HOME, then standard DSH home
    candidates. A candidate only counts when its server answers the token
    exchange AND the configured provider has its API key present (checked
    by variable name only, never by value). With launch=True the launch
    path owns the DSH lifecycle: any running DSH web instance is stopped
    first, a fresh one is started with the current configuration, and the
    provider check gates the result. Without a ready session the run
    stops with the concrete missing piece. Fail-closed.
    """
    candidates = []
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())
    candidates += [Path(p).expanduser() for p in DSH_HOME_CANDIDATES]

    if launch:
        running = _find_dsh_pids()
        if running:
            _stop_dsh_instances(running)
        blocked = _ensure_port_free_for_dsh(3080)
        if blocked:
            return None, blocked
        process = None
        try:
            process, client = launch_dsh_web()
        except Exception as e:
            return None, f"dsh web no arrancó: {e}"

        # Auth preference: the durable HMAC cookie from the DSH home. The
        # console token is single-use and races with the browser dsh web
        # auto-opens, which surfaces as HTTP 401 on exchange.
        port = int(client.base_url.rsplit(":", 1)[1])
        home = _provider_home(candidates)
        verified = False
        if home is not None:
            try:
                home_client = DshLocalClient.from_dsh_home(home, port=port)
                home_client.list_sessions()
                client = home_client
                verified = True
            except Exception:
                verified = False
        if not verified:
            last_error = "sin intento de canje"
            for _attempt in range(3):
                try:
                    client.exchange_token()
                    verified = True
                    break
                except Exception as e:
                    last_error = str(e)
                    time.sleep(1)
            if not verified:
                if process is not None:
                    process.kill()
                return None, (f"DSH no quedó autenticado tras el arranque: "
                              f"{last_error}")
        home = _provider_home(candidates)
        if home is None:
            process.kill()
            return None, ("no se encontró settings.yaml de DSH; define "
                          "DSH_HOME y configura el proveedor")
        status = dsh_provider_status(home)
        if not status["ok"] and os.environ.get("DSH_PROVIDER_STRICT"):
            process.kill()
            return None, status["reason"]
        return client, _provider_gate_origin(status)

    last_error = "sin candidatos"
    for home in candidates:
        try:
            client = DshLocalClient.from_dsh_home(home)
            client.exchange_token()
        except Exception as e:
            last_error = str(e)
            continue
        status = dsh_provider_status(home)
        if not status["ok"] and os.environ.get("DSH_PROVIDER_STRICT"):
            return None, status["reason"]
        return client, _provider_gate_origin(status, origin=str(home))
    return None, (
        "sin sesión DSH autenticada "
        f"(última prueba: {last_error}); abre 'dsh web' y reejecuta, "
        "define DSH_HOME o usa --launch-dsh")


CREATOR_SESSION_FILE = "creator-session.json"
ACTIVE_JOB_STATES = {"running", "stopping"}


def _session_state_path(run_dir):
    return Path(run_dir) / CREATOR_SESSION_FILE


def _save_session_state(run_dir, state, *, reason=None, now_fn=time.time):
    state = dict(state)
    if reason is not None:
        state["reason"] = reason
    state["updated_at"] = _now_iso()
    _update_json(_session_state_path(run_dir), state)
    return state


def _new_session_state(run_dir, prep, run_doc, *, now_fn=time.time):
    now = now_fn()
    budget = run_doc.get("budget") or {}
    max_seconds = int(budget.get("max_seconds", 1800))
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": prep["generation_id"],
        "session_id": "session-creator-" + secrets.token_hex(16),
        "request_id": "creator-request-" + secrets.token_hex(16),
        "prompt_digest": prep["prompt_digest"],
        "deadline": now + max_seconds,
        "cursor": -1,
        "reason": "DISPATCH_PENDING",
        "created_at": _now_iso(),
    }


def _load_or_create_session_state(run_dir, prep, run_doc, *, now_fn=time.time):
    path = _session_state_path(run_dir)
    if path.is_file():
        state = _read_json(path)
        required = {"session_id", "request_id", "prompt_digest", "deadline",
                    "cursor", "reason"}
        missing = sorted(required - set(state))
        if missing:
            raise ValueError("creator-session.json incompleto: " + ", ".join(missing))
        if state["prompt_digest"] != prep["prompt_digest"]:
            raise ValueError("creator-session.json no corresponde al prompt persistido")
        if state.get("generation_id") != prep["generation_id"]:
            raise ValueError("creator-session.json no corresponde a este run")
        return state, False
    state = _new_session_state(run_dir, prep, run_doc, now_fn=now_fn)
    _write_json(path, state)
    return state, True


def _call_create_session(client, run_dir, session_id):
    """Use explicit identity, retaining compatibility with narrow test fakes."""
    try:
        return client.create_creator_session(
            workspace_path=_run_workspace(run_dir), session_id=session_id)
    except TypeError as exc:
        if "session_id" not in str(exc):
            raise
        created = client.create_creator_session(workspace_path=_run_workspace(run_dir))
        if created != session_id:
            raise ValueError("El cliente DSH no admite reanudación con session_id")
        return created


def _call_send_prompt(client, session_id, prompt, request_id):
    try:
        return client.send_prompt(session_id, prompt, request_id=request_id)
    except TypeError as exc:
        if "request_id" not in str(exc):
            raise
        return client.send_prompt(session_id, prompt)


def _manifest_exists(run_dir):
    return (Path(run_dir) / "generated" / "generation-manifest.json").is_file()


def _event_request_id(event):
    """Extract only the durable direct-user RPC identity, never fuzzy JSON."""
    if event.get("type") != "user/message":
        return None
    data = event.get("data") or {}
    message = data.get("message", data) if isinstance(data, dict) else {}
    source = message.get("source") if isinstance(message, dict) else None
    return source.get("rpcId") if isinstance(source, dict) else None


def _fold_observation(state, observation):
    events = observation.get("events") or []
    request_seen = bool(state.get("request_seen"))
    request_turn = state.get("request_turn")
    terminal = bool(state.get("terminal"))
    terminal_reason = state.get("terminal_reason")
    cursor = state.get("cursor", -1)
    open_turn = state.get("open_turn")
    for event in events:
        if not isinstance(event, dict):
            continue
        seq = event.get("seq")
        if isinstance(seq, int):
            cursor = max(cursor, seq)
        data = event.get("data") or {}
        if event.get("type") == "turn/start" and isinstance(data, dict):
            open_turn = data.get("turn")
        if _event_request_id(event) == state["request_id"]:
            event_turn = data.get("turn") if isinstance(data, dict) else None
            request_turn = event_turn if isinstance(event_turn, int) else open_turn
            if not isinstance(request_turn, int):
                raise ValueError("user/message Creator no puede correlacionarse a un turno")
            request_seen = True
        if event.get("type") == "turn/end" and isinstance(data, dict):
            if request_turn is not None and data.get("turn") == request_turn:
                terminal = True
                terminal_reason = data.get("reason", "turn/end")
    observed_cursor = observation.get("cursor")
    if isinstance(observed_cursor, int):
        cursor = max(cursor, observed_cursor)
    descendants = observation.get(
        "descendants", observation.get("children", [])) or []
    descendant_running = any(
        bool(descendant.get("running")) for descendant in descendants
        if isinstance(descendant, dict))
    jobs = observation.get("jobs") or []
    active_jobs = any(job.get("status") in ACTIVE_JOB_STATES for job in jobs
                      if isinstance(job, dict))
    state.update({
        "cursor": cursor,
        "request_seen": request_seen,
        "request_turn": request_turn,
        "open_turn": open_turn,
        "terminal": terminal,
        "terminal_reason": terminal_reason,
        "running": bool(observation.get("running")),
        "descendant_running": descendant_running,
        "child_running": descendant_running,
        "active_jobs": active_jobs,
    })
    state["quiescent"] = (terminal and not state["running"] and
                          not descendant_running and not active_jobs)
    return state


def _mark_recovery_required(session, state, reason):
    run_doc = _read_json(session.run_dir / "run.json")
    run_doc["status"] = "RECOVERY_REQUIRED"
    run_doc["updated_at"] = _now_iso()
    _update_json(session.run_dir / "run.json", run_doc)
    _save_session_state(session.run_dir, state, reason=reason)
    return {
        "result": "RECOVERY_REQUIRED",
        "generation_id": run_doc.get("generation_id", "unknown"),
        "dsh_session_id": state.get("session_id"),
        "reason": reason,
    }


def _observe_creator(client, state):
    observer = getattr(client, "creator_observation", None)
    if observer is None:
        raise ValueError("Cliente DSH sin API durable de observación Creator")
    return observer(state["session_id"], cursor=state.get("cursor", -1))


def _supervise_creator(session, client, state, *, poll_seconds=5,
                       cancel_grace_seconds=30, now_fn=time.time,
                       sleep_fn=time.sleep):
    """Require correlated ``turn/end`` and whole-session quiescence."""
    while True:
        observation = _observe_creator(client, state)
        _fold_observation(state, observation)
        _save_session_state(session.run_dir, state, reason="OBSERVING")

        if state.get("quiescent"):
            if _manifest_exists(session.run_dir):
                _save_session_state(session.run_dir, state,
                                    reason="TERMINAL_QUIESCENT")
                try:
                    manifest = session.verify_generation_output()
                except HostPrevalidationFailed as exc:
                    # The Creator turn is terminal and the whole session is
                    # quiescent: do not retain here (which would strand the
                    # Host chain) and never redispatch this immutable turn.
                    # Acceptance owns the authoritative RETAINED transition
                    # and binds the rejected candidate in static-retained.json.
                    _save_session_state(
                        session.run_dir, state,
                        reason="READY_FOR_HOST_REJECTION")
                    return {
                        "result": "READY_FOR_HOST_REJECTION",
                        "generation_id": state.get("generation_id", "unknown"),
                        "dsh_session_id": state.get("session_id"),
                        "reason": str(exc),
                    }
                return session.create_finish(manifest)
            reason = "Creator terminó y quedó quiescente sin generation-manifest.json"
            _save_session_state(session.run_dir, state,
                                reason="TERMINAL_WITHOUT_MANIFEST")
            return session.retain(reason)

        now = now_fn()
        if now >= state["deadline"]:
            _save_session_state(session.run_dir, state, reason="CANCELLING_TIMEOUT")
            try:
                client.cancel_session(state["session_id"])
            except Exception as exc:
                return _mark_recovery_required(
                    session, state, f"Timeout; cancelación DSH no confirmada: {exc}")
            cancel_deadline = now + cancel_grace_seconds
            while now_fn() <= cancel_deadline:
                observation = _observe_creator(client, state)
                _fold_observation(state, observation)
                _save_session_state(session.run_dir, state,
                                    reason="WAITING_FOR_QUIESCENCE")
                if (not state.get("running") and
                        not state.get("descendant_running") and
                        not state.get("active_jobs")):
                    reason = ("Timeout de Creator; cancelación confirmada y "
                              "sesión quiescente")
                    _save_session_state(session.run_dir, state,
                                        reason="CANCELLED_QUIESCENT")
                    return session.retain(reason)
                sleep_fn(poll_seconds)
            return _mark_recovery_required(
                session, state,
                "Timeout de Creator; no se confirmó quiescencia tras cancelar")

        # A terminal event is insufficient while the parent, any transitive
        # descendant, or any reached session's job remains active.
        sleep_fn(poll_seconds)


def run_creator(run_dir, *, client=None, acquire=False, launch=False, wait=True,
                poll_seconds=5, cancel_grace_seconds=30, now_fn=time.time,
                sleep_fn=time.sleep):
    """Execute or idempotently resume one durably supervised Creator run."""
    run_dir = Path(run_dir)
    with _run_lock(run_dir):
        run_doc = _read_json(run_dir / "run.json")
        budget = run_doc.get("budget") or {}
        session = CreatorSession(
            run_dir,
            timeout_seconds=int(budget.get("max_seconds", 1800)),
            max_tokens=int(budget.get("max_tokens", 500000)),
        )
        try:
            # A completed valid run is immutable from Creator's perspective.
            # Verify and return it before prepare() can rewrite status/checkpoint
            # or any DSH call can redispatch the prompt.
            if run_doc.get("status") == "GENERATED":
                manifest = session.verify_generation_output()
                finish_path = run_dir / "finish.json"
                if not finish_path.is_file():
                    return session.create_finish(manifest)
                finish = _read_json(finish_path)
                expected = _digest_bytes(
                    json.dumps(manifest, sort_keys=True).encode("utf-8"))
                if (finish.get("status") != "GENERATED" or
                        finish.get("generation_id") != manifest.get("generation_id") or
                        finish.get("manifest_digest") != expected):
                    raise ValueError("finish.json no corresponde al manifest GENERATED")
                return {
                    "result": "GENERATED",
                    "generation_id": manifest.get("generation_id", "unknown"),
                    "artifact_count": len(manifest.get("artifacts", [])),
                }
            prep = session.prepare()
            prompt_text = Path(prep["prompt_path"]).read_text(encoding="utf-8")
            # This Host-owned record is durable before any session/create or
            # session/prompt RPC, enabling exact adoption after interruption.
            state, created_state = _load_or_create_session_state(
                run_dir, prep, run_doc, now_fn=now_fn)

            # A previously observed terminal/quiescent turn is immutable. If
            # its package failed Host prevalidation, return control to the
            # Host boundary without adopting the session or replaying prompt.
            if (state.get("terminal") and state.get("quiescent")
                    and _manifest_exists(run_dir)):
                try:
                    manifest = session.verify_generation_output()
                except HostPrevalidationFailed as exc:
                    _save_session_state(
                        run_dir, state, reason="READY_FOR_HOST_REJECTION")
                    return {
                        "result": "READY_FOR_HOST_REJECTION",
                        "generation_id": prep["generation_id"],
                        "dsh_session_id": state.get("session_id"),
                        "reason": str(exc),
                    }
                return session.create_finish(manifest)

            dsh_origin = None
            if client is None and acquire:
                client, dsh_origin = acquire_dsh_client(launch=launch)
                if client is None:
                    _save_session_state(run_dir, state, reason="AWAITING_DSH")
                    return {
                        "result": "PREPARED",
                        "generation_id": prep["generation_id"],
                        "prompt_path": prep["prompt_path"],
                        "dsh_session_id": state["session_id"],
                        "dsh_origin": dsh_origin,
                        "message": dsh_origin,
                    }

            if client is not None and getattr(client, "authenticated", False):
                adopted = _call_create_session(client, run_dir, state["session_id"])
                if adopted != state["session_id"]:
                    raise ValueError("DSH devolvió un session_id distinto del persistido")
                session._session_ref = adopted
                _save_session_state(run_dir, state, reason="SESSION_ADOPTED")
                # DSH session/prompt deduplicates the stable requestId against
                # durable and queued user messages, so replay is intentional.
                _call_send_prompt(client, adopted, prompt_text, state["request_id"])
                _save_session_state(run_dir, state, reason="PROMPT_ACCEPTED")

                if wait:
                    return _supervise_creator(
                        session, client, state, poll_seconds=poll_seconds,
                        cancel_grace_seconds=cancel_grace_seconds,
                        now_fn=now_fn, sleep_fn=sleep_fn)

            return {
                "result": "PREPARED",
                "generation_id": prep["generation_id"],
                "prompt_path": prep["prompt_path"],
                "dsh_session_id": state["session_id"],
                "dsh_origin": dsh_origin,
                "message": ("Run enviado/reanudado idempotentemente en DSH Creator"
                            if session._session_ref else
                            "Run preparado; Creator debe ejecutarse para generar paquete"),
            }
        except ValueError as exc:
            return session.retain(str(exc))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True,
                        help="Ruta al directorio del run (creator-runs/<id>)")
    parser.add_argument("--launch-dsh", action="store_true",
                        help="Arrancar 'dsh web' como proceso hijo si no hay "
                             "sesión autenticada (DSH debe estar instalado)")
    args = parser.parse_args()

    result = run_creator(args.run_dir, acquire=True, launch=args.launch_dsh)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("result") == "RETAINED":
        sys.exit(1)


if __name__ == "__main__":
    main()
