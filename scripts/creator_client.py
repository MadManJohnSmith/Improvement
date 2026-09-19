"""Automatización DSH Creator — C2.

Cliente Host-side que crea una sesión Creator, envía el prompt versionado
y supervisa la generación sin persistir credenciales ni auto-aprobarse.

    python3 -B scripts/creator_client.py --run-dir <creator-runs/gen-id>

Versión: 1
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
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


def _write_json(path, value):
    p = Path(path) if not isinstance(path, Path) else path
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _update_json(path, value):
    """Overwrite an existing JSON file (for status updates)."""
    p = Path(path)
    if p.is_file():
        p.unlink()
    _write_json(p, value)


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
    workspace = run_dir.parent.parent if run_dir.parent.name == "creator-runs" else run_dir.parent
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

## Invariantes

1. Solo emitir status GENERATED; nunca ACCEPTED/ACTIVE
2. Exactamente dos modos finales específicos del proyecto
3. No modificar Host, validadores, tests, holdouts, capabilities ni acceptance
4. No rutas/identidades/secretos del mantenedor
5. No proveedores/modelos/routing nuevos
6. Todo valor/decisión tiene fuente
7. Unknowns load-bearing bloquean la generación

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

    def create_creator_session(self, *, cwd, agent_preset="cordis"):
        """Create a session and queue the Creator prompt through DSH."""
        req = {"cwd": str(cwd)}
        if agent_preset:
            req["agentPreset"] = agent_preset
        created = self.rpc("session/create", {"request": req})
        value = created.get("value", created) if isinstance(created, dict) else created
        session_id = value.get("sessionId") if isinstance(value, dict) else None
        if not session_id:
            raise ValueError("DSH session/create returned no sessionId")
        return session_id

    def send_prompt(self, session_id, prompt):
        """Queue a text prompt; returns the Host receipt."""
        return self.rpc("session/prompt", {"request": {
            "requestId": secrets.token_hex(16),
            "sessionId": session_id,
            "mode": "queue",
            "content": [{"type": "text", "text": prompt}],
        }})


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

    def check_budget(self):
        """Check whether we're within budget limits."""
        if self.start_time is None:
            return True

        elapsed = time.time() - self.start_time
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
        list(command), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, bufsize=1, env=child_env,
    )
    captured = []
    deadline = time.time() + spawn_timeout
    url_line = None
    while time.time() < deadline:
        line = process.stdout.readline()
        if not line:
            break
        captured.append(line.rstrip())
        if "dsh web:" in line and "?token=" in line:
            url_line = line
            break
        if process.poll() is not None:
            break
    if url_line:
        return process, DshLocalClient.from_console_line(url_line)
    process.kill()
    tail = re.sub(r"\?token=\S+", "?token=<redacted>",
                  "\n".join(captured[-15:])) or "<sin salida>"
    raise RuntimeError(
        "DSH no imprimió una URL autenticada (exit="
        f"{process.poll()}); salida capturada sin token:\n{tail}")


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
        if "@deepseek-ai/dsh" in cmdline and (
                " web" in cmdline or "--profile web" in cmdline):
            pids.append(pid)
    return pids


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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
        try:
            process, client = launch_dsh_web()
        except Exception as e:
            return None, f"dsh web no arrancó: {e}"
        home = _provider_home(candidates)
        if home is None:
            process.kill()
            return None, ("no se encontró settings.yaml de DSH; define "
                          "DSH_HOME y configura el proveedor")
        status = dsh_provider_status(home)
        if not status["ok"]:
            process.kill()
            return None, status["reason"]
        return client, f"launched:dsh-web ({status['provider']})"

    last_error = "sin candidatos"
    for home in candidates:
        try:
            client = DshLocalClient.from_dsh_home(home)
            client.exchange_token()
        except Exception as e:
            last_error = str(e)
            continue
        status = dsh_provider_status(home)
        if not status["ok"]:
            return None, status["reason"]
        return client, str(home)
    return None, (
        "sin sesión DSH autenticada "
        f"(última prueba: {last_error}); abre 'dsh web' y reejecuta, "
        "define DSH_HOME o usa --launch-dsh")


def _wait_for_generation(session, *, poll_seconds=5):
    """Poll until the package is generated or the budget expires.

    Budget exhaustion raises ValueError (handled as RETAINED upstream).
    Returns True when generated/ contains a manifest (or the run left
    GENERATING because the Host took over), False when the budget ran out
    without output.
    """
    session.start_time = time.time()
    while True:
        session.check_budget()
        gen_manifest = session.run_dir / "generated" / "generation-manifest.json"
        if gen_manifest.is_file():
            return True
        run_doc = _read_json(session.run_dir / "run.json")
        if run_doc.get("status") != "GENERATING":
            return gen_manifest.is_file()
        time.sleep(poll_seconds)


def run_creator(run_dir, *, client=None, acquire=False, launch=False, wait=True):
    """Execute the Creator pipeline for a run.

    Returns the result dict. Validates the structure, builds the prompt,
    dispatches through DSH when a client is injected or acquirable, waits
    for the generated package within budget, and verifies it. Without an
    authenticated DSH session the run stays in a recoverable PREPARED
    state; nothing is silently skipped.
    """
    run_dir = Path(run_dir)
    session = CreatorSession(
        run_dir,
        timeout_seconds=1800,
        max_tokens=500000,
    )

    try:
        # Prepare: validate, build prompt, update status
        prep = session.prepare()

        prompt_path = Path(prep["prompt_path"])
        prompt_text = prompt_path.read_text(encoding="utf-8")

        dsh_origin = None
        if client is None and acquire:
            client, dsh_origin = acquire_dsh_client(launch=launch)
            if client is None:
                return {
                    "result": "PREPARED",
                    "generation_id": prep["generation_id"],
                    "prompt_path": prep["prompt_path"],
                    "dsh_session_id": None,
                    "dsh_origin": dsh_origin,
                    "message": dsh_origin,
                }

        # If client authenticated, dispatch to DSH
        session_id = None
        if client is not None and getattr(client, "authenticated", False):
            session_id = client.create_creator_session(cwd=run_dir)
            session._session_ref = session_id
            client.send_prompt(session_id, prompt_text)

        # Verify that if outputs exist, they're valid
        gen_dir = run_dir / "generated"
        if gen_dir.is_dir() and (gen_dir / "generation-manifest.json").is_file():
            manifest = session.verify_generation_output()
            return session.create_finish(manifest)

        if session_id and wait:
            generated = _wait_for_generation(session)
            if generated:
                manifest = session.verify_generation_output()
                return session.create_finish(manifest)
            return {
                "result": "DISPATCHED",
                "generation_id": prep["generation_id"],
                "prompt_path": prep["prompt_path"],
                "dsh_session_id": session_id,
                "dsh_origin": dsh_origin,
                "message": "Presupuesto de supervisión agotado sin paquete; "
                           "el run continúa y es reanudable",
            }

        return {
            "result": "PREPARED",
            "generation_id": prep["generation_id"],
            "prompt_path": prep["prompt_path"],
            "dsh_session_id": session_id,
            "dsh_origin": dsh_origin,
            "message": "Run preparado y enviado a DSH Creator" if session_id else "Run preparado; Creator debe ejecutarse para generar paquete",
        }

    except ValueError as e:
        return session.retain(str(e))


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
