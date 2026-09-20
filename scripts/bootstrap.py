#!/usr/bin/env python3
"""Bootstrap determinista para generación de modos y skills específicos.

Subcomandos:
    install     Flujo completo: preflight, Creator, aceptación Host y activación
    accept      Solicitar validación Host de un paquete generado (invocado por Creator)
    finalize    Reanudar aceptación Host y activar si el veredicto es ACTIVE
    verify-acceptance  Consultar veredicto, evidencia y despliegue activo
    update      Regenerar sobre base material cambiada
    uninstall   Retirar modos/skills gestionados sin tocar producto
    purge-data  Eliminar datos de runs (destructivo, separado, con confirmación)

    python3 -B scripts/bootstrap.py install --project /ruta/proyecto --launch-dsh
    python3 -B scripts/bootstrap.py finalize --workspace /ws --generation-id gen-id
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK / "scripts"))

from onboard import checked, framework_clean, prepare_project_skills

SCHEMA_VERSION = 1
RUN_DIR_NAME = "creator-runs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path, value):
    """Write JSON to a new file exclusively (O_EXCL). Fail if exists."""
    p = checked(path) if isinstance(path, str) else path
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _read_json(path):
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise ValueError(f"Archivo ausente o enlace simbólico: {path}")
    if p.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Archivo excesivo: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _generation_id():
    return f"gen-{uuid.uuid4().hex[:12]}"


def _git_info(repo_path):
    """Get git revision and clean status without executing project code."""
    repo = checked(repo_path)
    if not (repo / ".git").is_dir():
        return {"revision": None, "clean": None, "branch": None}
    try:
        rev = subprocess.run(
            ["git", "-C", str(repo), "--no-optional-locks", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        branch = subprocess.run(
            ["git", "-C", str(repo), "--no-optional-locks", "rev-parse",
             "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(repo), "--no-optional-locks", "status",
             "--porcelain"],
            capture_output=True, text=True, check=False,
        )
        return {
            "revision": rev.stdout.strip() if rev.returncode == 0 else None,
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "clean": not bool(status.stdout) if status.returncode == 0 else None,
        }
    except FileNotFoundError:
        return {"revision": None, "clean": None, "branch": None}


def _root_identity(project, project_git):
    """Base identity used by install and update consistently.

    A full sha256 revision is used verbatim; any other revision is
    digested; the project path is only a last-resort identity. install
    and update must derive it the same way or drift detection breaks.
    """
    rev = (project_git or {}).get("revision")
    if rev and len(rev) == 64 and all(c in "0123456789abcdef" for c in rev.lower()):
        return rev.lower()
    if rev:
        return _digest_bytes(rev.encode("utf-8"))
    return _digest_bytes(str(project).encode("utf-8"))


def _detect_languages(project):
    """Detect languages from file extensions without reading file contents."""
    extensions = set()
    try:
        for item in project.rglob("*"):
            if item.is_file() and not item.is_symlink():
                ext = item.suffix.lower()
                if ext:
                    extensions.add(ext)
    except PermissionError:
        pass
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "javascript", ".tsx": "typescript", ".rb": "ruby",
        ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
        ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c",
        ".swift": "swift", ".php": "php", ".scala": "scala",
        ".ex": "elixir", ".exs": "elixir", ".hs": "haskell",
        ".lua": "lua", ".r": "r", ".jl": "julia", ".sh": "shell",
        ".bash": "shell", ".zsh": "shell",
    }
    return sorted({lang_map[e] for e in extensions if e in lang_map})


def _detect_areas(project):
    """Detect top-level areas without reading file contents."""
    areas = []
    try:
        for item in sorted(project.iterdir()):
            if item.is_dir() and not item.is_symlink() and not item.name.startswith("."):
                count = sum(1 for f in item.rglob("*") if f.is_file() and not f.is_symlink())
                if count > 0:
                    areas.append({
                        "name": item.name,
                        "path": item.name + "/",
                        "file_count": count,
                    })
    except PermissionError:
        pass
    return areas


def _count_files(project):
    """Count regular files and total bytes without reading contents."""
    total_files = 0
    total_bytes = 0
    try:
        for item in project.rglob("*"):
            if item.is_file() and not item.is_symlink():
                total_files += 1
                total_bytes += item.stat().st_size
    except PermissionError:
        pass
    return total_files, total_bytes


def _detect_instructions(project):
    """Detect instruction files (AGENTS.md, .agents/, etc.) without reading contents."""
    entries = []
    candidates = [
        ("AGENTS.md", "workspace", 10),
        (".agents/AGENTS.md", "workspace", 10),
        ("README.md", "workspace", 5),
        (".github/AGENTS.md", "workspace", 8),
    ]
    for rel, scope, precedence in candidates:
        p = project / rel
        if p.is_file() and not p.is_symlink():
            entries.append({
                "path": rel,
                "scope": scope,
                "precedence": precedence,
                "sha256": _digest_file(p),
            })
    return entries


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def preflight(project, workspace):
    """Validate paths, check DSH/Creator availability, detect capabilities.

    Returns a dict with preflight results. Raises ValueError on failure.
    """
    project = checked(project)
    workspace = checked(workspace)

    if not project.is_dir():
        raise ValueError(f"Proyecto no existe: {project}")

    # Overlap checks
    if workspace == project or workspace in project.parents or project in workspace.parents:
        raise ValueError("Workspace debe ser externo al proyecto")
    if workspace == FRAMEWORK or workspace in FRAMEWORK.parents or FRAMEWORK in workspace.parents:
        raise ValueError("Workspace debe ser externo al framework")
    if project == FRAMEWORK or project in FRAMEWORK.parents or FRAMEWORK in project.parents:
        raise ValueError("Proyecto debe ser externo al framework")

    # Workspace parent must exist
    if not workspace.parent.is_dir():
        raise ValueError(f"Padre del workspace no existe: {workspace.parent}")

    # Check for symlinks in workspace path
    for part in [*reversed(workspace.parents), workspace]:
        if part.is_symlink():
            raise ValueError(f"Enlace simbólico en ruta del workspace: {part}")

    # Check for symlinks in project path
    for part in [*reversed(project.parents), project]:
        if part.is_symlink():
            raise ValueError(f"Enlace simbólico en ruta del proyecto: {part}")

    # Workspace cannot be inside a git repo (checked in onboard.py too)
    for parent in [workspace.parent, *workspace.parent.parents]:
        if (parent / ".git").exists() or (parent / ".git").is_symlink():
            raise ValueError("Workspace no puede estar dentro de un repositorio Git")

    # DSH availability check
    dsh_info = _check_dsh()

    # Framework clean check
    fw_clean = framework_clean()

    return {
        "project": str(project),
        "workspace": str(workspace),
        "framework": str(FRAMEWORK),
        "framework_clean": fw_clean,
        "dsh": dsh_info,
        "timestamp": _now_iso(),
    }


def _check_dsh():
    """Check DSH installation and Creator availability.

    Returns a dict with DSH info. Does not open credentials.
    """
    dsh_root = os.environ.get("DSH_MODULE_ROOT")
    info = {
        "available": False,
        "module_root": dsh_root,
        "creator_available": False,
        "version": None,
    }

    if not dsh_root:
        return info

    dsh_path = Path(dsh_root)
    if dsh_path.is_dir():
        info["available"] = True
        # Check for Creator presence
        try:
            result = subprocess.run(
                ["node", "-e",
                 "try{const p=require(process.env.DSH_MODULE_ROOT+"
                 "'/package.json');console.log(JSON.stringify("
                 "{version:p.version||null}))}catch(e){"
                 "console.log(JSON.stringify({version:null}))}"],
                capture_output=True, text=True, check=False,
                timeout=10,
            )
            if result.returncode == 0:
                parsed = json.loads(result.stdout.strip())
                info["version"] = parsed.get("version")
                info["creator_available"] = True
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

    return info


# ---------------------------------------------------------------------------
# install subcommand
# ---------------------------------------------------------------------------


def _dispatch_creator_chain(result, run_dir, launch_dsh, finalize_host=True):
    """Dispatch Creator, then let deterministic Host code accept and activate.

    Creator remains unable to self-approve: it can only produce GENERATED and
    request acceptance. The Host-side chain runs after that session returns.
    Failures remain recoverable and are reported without granting activation.
    """
    sys.path.insert(0, str(FRAMEWORK / "scripts"))
    import creator_client as cc
    try:
        result["creator"] = cc.run_creator(
            run_dir, acquire=True, launch=launch_dsh)
    except Exception as e:
        result["creator"] = {
            "result": "PREPARED",
            "generation_id": result.get("generation_id"),
            "error": str(e),
            "message": "Despacho a Creator falló; run recuperable",
        }
    creator_state = result["creator"].get("result")
    detail = result["creator"].get("message") or result["creator"].get("error")
    if detail:
        result["message"] += f"; Creator: {creator_state} ({detail})"
    else:
        result["message"] += f"; Creator: {creator_state}"

    if finalize_host and creator_state == "GENERATED":
        workspace = Path(run_dir).parent.parent
        try:
            result["host"] = finalize(
                workspace, generation_id=result.get("generation_id"))
        except Exception as e:
            result["host"] = {
                "result": "FINALIZATION_FAILED",
                "generation_id": result.get("generation_id"),
                "error": str(e),
                "message": "Finalización Host falló; run recuperable",
            }
        host_state = result["host"].get("result")
        host_detail = result["host"].get("message") or result["host"].get("error")
        result["message"] += f"; Host: {host_state}"
        if host_detail:
            result["message"] += f" ({host_detail})"


def install(project, workspace, *, budget=None, dispatch_creator=False,
            launch_dsh=False, finalize_host=True):
    """Create a new generation run from preflight through Creator package.

    Idempotent: if an identical run already exists, returns its reference.
    Fail-closed: errors leave a checkpoint at RETAINED.
    """
    project = checked(project)
    workspace = checked(workspace)

    # Preflight
    pf = preflight(project, workspace)

    # Determine project name from directory name
    project_name = project.name.lower().replace(" ", "-")
    if not project_name:
        raise ValueError("No se puede derivar nombre del proyecto")

    # Create workspace if needed (idempotent)
    if workspace.exists():
        if not workspace.is_dir():
            raise ValueError(f"Workspace en conflicto: {workspace}")
        identity_file = workspace / "project.json"
        if identity_file.is_file():
            existing = _read_json(identity_file)
            if existing.get("name") != project_name:
                raise ValueError(
                    f"Workspace existente con identidad diferente: "
                    f"{existing.get('name')} != {project_name}"
                )
    else:
        workspace.mkdir(mode=0o700)
        identity = {"schema": 1, "name": project_name, "project": str(project)}
        _write_json(workspace / "project.json", identity)

    # Check for existing active generation (idempotent)
    runs_dir = workspace / RUN_DIR_NAME
    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if run_path.is_dir() and (run_path / "run.json").is_file():
                existing_run = _read_json(run_path / "run.json")
                status = existing_run.get("status")
                if status in ("CREATED", "DISCOVERING", "DESIGNING",
                              "GENERATING", "GENERATED", "VALIDATING",
                              "BACKED_UP", "STAGED", "ACCEPTING",
                              "REPAIRING"):
                    result = {
                        "result": "EXISTING",
                        "generation_id": existing_run.get("generation_id"),
                        "run_dir": str(run_path),
                        "status": status,
                        "message": f"Generación existente en progreso: {status}",
                    }
                    if dispatch_creator and status in ("CREATED", "GENERATING"):
                        # Only these states are resumable by run_creator;
                        # dispatching others would wrongly retain the run.
                        _dispatch_creator_chain(
                            result, run_path, launch_dsh, finalize_host)
                    return result
                if status == "ACTIVE":
                    project_git = _git_info(project)
                    if (existing_run.get("project", {}).get("root_identity")
                            == project_git.get("revision")):
                        return {
                            "result": "NO_OP",
                            "generation_id": existing_run.get("generation_id"),
                            "run_dir": str(run_path),
                            "status": "ACTIVE",
                            "message": "Generación activa con la misma base; no-op",
                        }

    # Generate new run
    gen_id = _generation_id()
    run_dir = runs_dir / gen_id

    if run_dir.exists():
        raise ValueError(f"Run ya existe: {run_dir}")

    # Create run directory structure
    run_dir.mkdir(mode=0o700, parents=True)
    for subdir in ("inputs", "discovery", "design", "tests",
                   "generated", "validation", "acceptance",
                   "retained", "backup", "promotion"):
        (run_dir / subdir).mkdir(mode=0o700)

    # Git info
    project_git = _git_info(project)
    framework_git = _git_info(FRAMEWORK)

    # Root identity (always sha256, derived identically for update())
    root_identity = _root_identity(project, project_git)

    # Create run.json
    run_doc = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "status": "CREATED",
        "created_at": _now_iso(),
        "project": {
            "name": project_name,
            "root_identity": root_identity,
        },
        "framework_revision": framework_git.get("revision") or "unknown",
        "budget": budget or {
            "max_attempts": 3,
            "max_tokens": 500000,
            "max_seconds": 1800,
        },
        "directories": {
            "inputs": "inputs",
            "discovery": "discovery",
            "design": "design",
            "tests": "tests",
            "generated": "generated",
            "validation": "validation",
            "acceptance": "acceptance",
            "retained": "retained",
            "backup": "backup",
            "promotion": "promotion",
        },
    }
    _write_json(run_dir / "run.json", run_doc)

    # Library snapshot: selection inputs are frozen per run (provenance)
    library_digest = None
    library_path = FRAMEWORK / "library" / "library.json"
    if library_path.is_file() and not library_path.is_symlink():
        sys.path.insert(0, str(FRAMEWORK / "scripts"))
        import generation_contracts as gc
        library_doc = _read_json(library_path)
        gc.validate("library", library_doc)
        _write_json(run_dir / "inputs" / "library.json", library_doc)
        library_digest = _digest_file(library_path)

    # Create inputs/bootstrap-request.json
    _write_json(run_dir / "inputs" / "bootstrap-request.json", {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "project": str(project),
        "workspace": str(workspace),
        "framework": str(FRAMEWORK),
        "library_sha256": library_digest,
        "timestamp": _now_iso(),
        "dsh": pf["dsh"],
    })

    # Create inputs/snapshot.json
    _write_json(run_dir / "inputs" / "snapshot.json", {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "path": str(project),
            "git": project_git,
        },
        "framework": {
            "path": str(FRAMEWORK),
            "git": framework_git,
            "clean": pf["framework_clean"],
        },
        "timestamp": _now_iso(),
    })

    # Create inputs/inventory.json
    total_files, total_bytes = _count_files(project)
    languages = _detect_languages(project)
    areas = _detect_areas(project)

    _write_json(run_dir / "inputs" / "inventory.json", {
        "schema_version": SCHEMA_VERSION,
        "project_name": project_name,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "languages": languages,
        "areas": areas,
    })

    # Create inputs/authority.json
    _write_json(run_dir / "inputs" / "authority.json", {
        "schema_version": SCHEMA_VERSION,
        "holder": "user",
        "source": "bootstrap-install",
        "allowed_data": ["product_read", "framework_execute", "workspace_write"],
        "budget": run_doc["budget"],
    })

    # Create inputs/host-policy.json
    _write_json(run_dir / "inputs" / "host-policy.json", {
        "schema_version": SCHEMA_VERSION,
        "immutable_controls": True,
        "fail_closed": True,
        "no_credentials_in_artifacts": True,
        "no_local_paths_in_output": True,
        "creator_cannot_accept": True,
    })

    # Create inputs/effective-routing.json (digest only, no credentials)
    routing_digest = _digest_bytes(
        json.dumps(pf["dsh"], sort_keys=True).encode("utf-8")
    )
    _write_json(run_dir / "inputs" / "effective-routing.json", {
        "schema_version": SCHEMA_VERSION,
        "routing_digest": routing_digest,
        "timestamp": _now_iso(),
    })

    # Create inputs/runtime-capabilities.json
    _write_json(run_dir / "inputs" / "runtime-capabilities.json", {
        "schema_version": SCHEMA_VERSION,
        "capability_id": f"cap-{gen_id}",
        "session_id": gen_id,
        "project": project_name,
        "executor": "creator",
        "roots": {
            "product_read": [str(project)],
            "framework_execute": [str(FRAMEWORK)],
            "workspace_write": [str(workspace)],
        },
        "scope": ["audit", "repair", "generate"],
    })

    # Prepare general skills
    skills_source = FRAMEWORK / "skills"
    if skills_source.is_dir() and any(skills_source.iterdir()):
        try:
            prepare_project_skills(workspace, source=skills_source, apply=True)
        except ValueError:
            pass  # Already prepared or no portable skills

    # Create discovery/ initial files
    instructions = _detect_instructions(project)
    _write_json(run_dir / "discovery" / "instructions-index.json", {
        "schema_version": SCHEMA_VERSION,
        "entries": instructions,
    })

    _write_json(run_dir / "discovery" / "project-manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "name": project_name,
        "root_identity": root_identity,
        "base_revision": project_git.get("revision") or "unknown",
        "inventory": {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "languages": languages,
            "areas": areas,
        },
        "authority": {"holder": "user", "source": "bootstrap-install"},
    })

    # Create checkpoint.json
    _write_json(run_dir / "checkpoint.json", {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "phase": "CREATED",
        "completed_phases": ["preflight", "snapshot", "inventory", "skills"],
        "pending_phases": ["creator_call"],
        "timestamp": _now_iso(),
        "resumable": True,
    })

    result = {
        "result": "CREATED",
        "generation_id": gen_id,
        "run_dir": str(run_dir),
        "status": "CREATED",
        "project": project_name,
        "message": f"Run {gen_id} creado; listo para Creator",
    }

    if dispatch_creator:
        _dispatch_creator_chain(
            result, run_dir, launch_dsh, finalize_host)
    return result


# ---------------------------------------------------------------------------
# accept subcommand
# ---------------------------------------------------------------------------


def accept(workspace, generated_dir):
    """Request Host validation of a generated package.

    Called by Creator after generation is complete. This only submits
    the request; it does not install or self-approve.
    """
    workspace = checked(workspace)
    if workspace.name == RUN_DIR_NAME:
        workspace = workspace.parent
    generated = checked(generated_dir)

    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")
    if not generated.is_dir():
        raise ValueError(f"Directorio generado no existe: {generated}")

    # Verify generated/ contains a generation-manifest.json
    manifest_path = generated / "generation-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Falta generation-manifest.json en el paquete generado")
    if manifest_path.is_symlink():
        raise ValueError("generation-manifest.json es un enlace simbólico")

    manifest = _read_json(manifest_path)

    # Validate manifest against C0 schema
    sys.path.insert(0, str(FRAMEWORK / "scripts"))
    import generation_contracts as gc
    gc.validate("generation-manifest", manifest)

    # Verify all artifact hashes
    mismatches = gc.verify_manifest_hashes(manifest, str(generated))
    if mismatches:
        details = "; ".join(f"{p}: expected {e}, got {a}" for p, e, a in mismatches)
        raise ValueError(f"Hashes no coinciden: {details}")

    # Check no symlinks in generated tree
    gc.check_no_symlinks(str(generated))

    # Find the run directory (parent of generated/)
    run_dir = generated.parent
    run_json_path = run_dir / "run.json"
    if not run_json_path.is_file():
        raise ValueError("run.json no encontrado en el directorio padre de generated/")

    run_doc = _read_json(run_json_path)
    gen_id = run_doc.get("generation_id")

    # Create acceptance request
    _write_json(run_dir / "acceptance" / "request.json", {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "manifest_digest": _digest_file(manifest_path),
        "artifact_count": len(manifest["artifacts"]),
        "timestamp": _now_iso(),
        "source": "creator",
    })

    # Update run status to VALIDATING
    run_doc["status"] = "VALIDATING"
    run_doc["updated_at"] = _now_iso()
    run_path = run_dir / "run.json"
    run_path.unlink()
    _write_json(run_path, run_doc)

    # Update checkpoint
    cp_path = run_dir / "checkpoint.json"
    if cp_path.is_file():
        cp_path.unlink()
    _write_json(cp_path, {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "phase": "VALIDATING",
        "completed_phases": [
            "preflight", "snapshot", "inventory", "skills",
            "creator_call", "generation",
        ],
        "pending_phases": ["validation", "backup", "acceptance", "activation"],
        "timestamp": _now_iso(),
        "resumable": True,
    })

    return {
        "result": "ACCEPT_REQUESTED",
        "generation_id": gen_id,
        "manifest_digest": _digest_file(manifest_path),
        "artifact_count": len(manifest["artifacts"]),
        "message": "Solicitud de aceptación enviada al Host",
    }


# ---------------------------------------------------------------------------
# verify-acceptance subcommand
# ---------------------------------------------------------------------------


def _resolve_run_dir(workspace, generation_id=None):
    """Resolve a run directory: explicit id, active pointer, or newest run."""
    runs_dir = workspace / RUN_DIR_NAME
    if not runs_dir.is_dir():
        raise ValueError("No hay runs de generación en el workspace")
    if generation_id:
        target = runs_dir / generation_id
        if not target.is_dir():
            raise ValueError(f"Run no encontrado: {generation_id}")
        return target
    active_pointer = workspace / ".dsh-managed" / "ACTIVE"
    if active_pointer.is_file():
        active_id = active_pointer.read_text(encoding="utf-8").strip()
        if active_id and (runs_dir / active_id).is_dir():
            return runs_dir / active_id
    runs = [p for p in runs_dir.iterdir() if p.is_dir() and (p / "run.json").is_file()]
    if not runs:
        raise ValueError("No se encontraron ejecuciones válidas")
    return max(runs, key=lambda p: p.stat().st_mtime)


def verify_acceptance(workspace, generation_id=None):
    """Verify acceptance state of a generation run or active deployment.

    Inspects host-verdict.json, validation summary, active pointer, and evidence.
    """
    workspace = checked(workspace)
    if workspace.name == RUN_DIR_NAME:
        workspace = workspace.parent
    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")

    target_run_dir = _resolve_run_dir(workspace, generation_id)

    run_json = _read_json(target_run_dir / "run.json")
    gen_id = run_json.get("generation_id", target_run_dir.name)
    status = run_json.get("status", "UNKNOWN")

    verdict_path = target_run_dir / "acceptance" / "host-verdict.json"
    verdict_data = _read_json(verdict_path) if verdict_path.is_file() else None

    val_path = target_run_dir / "validation" / "summary.json"
    val_data = _read_json(val_path) if val_path.is_file() else None

    active_pointer = workspace / ".dsh-managed" / "ACTIVE"
    is_active = False
    if active_pointer.is_file():
        is_active = (active_pointer.read_text(encoding="utf-8").strip() == gen_id)

    ledger_path = target_run_dir / "acceptance" / "evidence-ledger.jsonl"
    ledger_entries = 0
    if ledger_path.is_file():
        ledger_entries = sum(1 for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip())

    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "run_status": status,
        "is_active_deployment": is_active,
        "host_verdict": verdict_data.get("verdict") if verdict_data else None,
        "static_validation_passed": val_data.get("passed") if val_data else None,
        "evidence_ledger_entries": ledger_entries,
        "acceptance_request_present": (target_run_dir / "acceptance" / "request.json").is_file(),
        "verified_at": _now_iso(),
    }


def finalize(workspace, generation_id=None):
    """Run Host acceptance and activate only an explicit ACTIVE verdict.

    This is Host-side deterministic code, never part of the Creator session.
    RETAINED pauses cleanly with evidence and no installation. Existing
    verdicts and byte-identical installations are reused idempotently.
    """
    workspace = checked(workspace)
    if workspace.name == RUN_DIR_NAME:
        workspace = workspace.parent
    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")
    run_dir = _resolve_run_dir(workspace, generation_id)
    run_doc = _read_json(run_dir / "run.json")
    gen_id = run_doc.get("generation_id", run_dir.name)
    generated = run_dir / "generated"
    request_path = run_dir / "acceptance" / "request.json"
    verdict_path = run_dir / "acceptance" / "host-verdict.json"

    if not generated.is_dir():
        raise ValueError(f"generated/ ausente: {generated}")
    if not request_path.is_file():
        raise ValueError(
            "Solicitud de aceptación ausente: Creator debe ejecutar accept antes de finalizar")

    if verdict_path.is_file():
        verdict = _read_json(verdict_path)
    else:
        import acceptance
        verdict = acceptance.accept(run_dir)

    verdict_name = verdict.get("verdict")
    if verdict.get("generation_id") not in (None, gen_id):
        raise ValueError("host-verdict corresponde a otra generación")
    if verdict_name == "RETAINED":
        return {
            "result": "RETAINED",
            "generation_id": gen_id,
            "verdict": verdict,
            "is_active_deployment": False,
            "message": (
                "Host retuvo el candidato; no se instaló nada. Revisar "
                "acceptance/host-verdict.json y evidence-ledger.jsonl"),
        }
    if verdict_name != "ACTIVE":
        raise ValueError(f"Veredicto Host no activable: {verdict_name!r}")

    import transaction
    activation = transaction.install(
        workspace, generated, gen_id, host_verdict=verdict_path)

    run_path = run_dir / "run.json"
    current = _read_json(run_path)
    if current.get("status") != "ACTIVE":
        current["status"] = "ACTIVE"
        current["updated_at"] = _now_iso()
        run_path.unlink()
        _write_json(run_path, current)

    checkpoint_path = run_dir / "checkpoint.json"
    if checkpoint_path.is_file():
        checkpoint_path.unlink()
    _write_json(checkpoint_path, {
        "schema_version": SCHEMA_VERSION,
        "generation_id": gen_id,
        "phase": "ACTIVE",
        "completed_phases": [
            "preflight", "snapshot", "inventory", "skills",
            "creator_call", "generation", "validation", "backup",
            "acceptance", "activation",
        ],
        "pending_phases": [],
        "timestamp": _now_iso(),
        "resumable": False,
    })
    return {
        "result": activation.get("result", "ACTIVE"),
        "generation_id": gen_id,
        "activation": activation,
        "is_active_deployment": True,
        "message": "Host aceptó y activó el paquete transaccionalmente",
    }


# ---------------------------------------------------------------------------
# update subcommand
# ---------------------------------------------------------------------------


def update(project, workspace):
    """Trigger regeneration when the project base has materially changed.

    If the active generation's base matches the current project revision,
    this is a no-op. Otherwise, creates a new run.
    """
    project = checked(project)
    workspace = checked(workspace)

    if not project.is_dir():
        raise ValueError(f"Proyecto no existe: {project}")
    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")

    # Find active generation
    runs_dir = workspace / RUN_DIR_NAME
    active_run = None
    in_progress_run = None
    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if run_path.is_dir() and (run_path / "run.json").is_file():
                run_doc = _read_json(run_path / "run.json")
                status = run_doc.get("status")
                if status == "ACTIVE":
                    active_run = run_doc
                elif status in ("CREATED", "DISCOVERING", "DESIGNING",
                                "GENERATING", "GENERATED", "VALIDATING",
                                "BACKED_UP", "STAGED", "ACCEPTING",
                                "REPAIRING"):
                    in_progress_run = run_doc

    # Check for in-progress generation first
    if in_progress_run is not None:
        return {
            "result": "IN_PROGRESS",
            "generation_id": in_progress_run.get("generation_id"),
            "status": in_progress_run.get("status"),
            "message": f"Generación en progreso: {in_progress_run.get('status')}; esperar antes de update",
        }

    if active_run is None:
        raise ValueError("No hay generación activa para actualizar; usar install primero")

    # Compare base identity derived the same way install() derives it
    project_git = _git_info(project)
    current_identity = _root_identity(project, project_git)
    active_identity = active_run.get("project", {}).get("root_identity")

    if current_identity == active_identity:
        return {
            "result": "NO_OP",
            "generation_id": active_run.get("generation_id"),
            "message": "Misma base; no-op",
        }

    # Create new run for update
    return install(project, workspace)


# ---------------------------------------------------------------------------
# uninstall subcommand
# ---------------------------------------------------------------------------


def uninstall(project, workspace):
    """Remove managed modes, skills, and links. Preserve product and foreign config."""
    project = checked(project)
    workspace = checked(workspace)

    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")

    removed = []

    # Find and mark active generation as ROLLED_BACK
    runs_dir = workspace / RUN_DIR_NAME
    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if run_path.is_dir() and (run_path / "run.json").is_file():
                run_doc = _read_json(run_path / "run.json")
                if run_doc.get("status") == "ACTIVE":
                    run_doc["status"] = "ROLLED_BACK"
                    run_doc["updated_at"] = _now_iso()
                    rp = run_path / "run.json"
                    rp.unlink()
                    _write_json(rp, run_doc)
                    removed.append(f"run:{run_doc.get('generation_id')}")

    # Remove managed skills from workspace
    skills_dir = workspace / ".agents" / "skills"
    manifest_path = workspace / ".agents" / "workflow-skills.json"
    if skills_dir.is_dir():
        # Only remove skills that came from our framework
        framework_skills = set()
        fw_skills = FRAMEWORK / "skills"
        if fw_skills.is_dir():
            framework_skills = {p.name for p in fw_skills.iterdir()
                                if p.is_dir() and (p / "SKILL.md").is_file()}
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir() and skill_dir.name in framework_skills:
                shutil.rmtree(skill_dir)
                removed.append(f"skill:{skill_dir.name}")

    if manifest_path.is_file():
        manifest_path.unlink()
        removed.append("manifest:workflow-skills.json")

    return {
        "result": "UNINSTALLED",
        "removed": removed,
        "preserved": ["product", "foreign-config", "receipts", "backups"],
        "message": f"Desinstalados {len(removed)} elementos gestionados",
    }


# ---------------------------------------------------------------------------
# purge-data subcommand
# ---------------------------------------------------------------------------


def purge_data(workspace, *, confirm=False):
    """Delete all generation run data. Destructive, requires confirmation."""
    workspace = checked(workspace)

    if not workspace.is_dir():
        raise ValueError(f"Workspace no existe: {workspace}")

    runs_dir = workspace / RUN_DIR_NAME
    if not runs_dir.is_dir():
        return {
            "result": "NO_DATA",
            "message": "No hay datos de generación para purgar",
        }

    # List what would be deleted
    run_dirs = sorted(
        p.name for p in runs_dir.iterdir() if p.is_dir()
    )

    if not confirm:
        return {
            "result": "DRY_RUN",
            "runs_to_delete": run_dirs,
            "path": str(runs_dir),
            "message": f"Se eliminarían {len(run_dirs)} runs; "
                       "pasar --confirm para ejecutar",
        }

    # Check no symlinks before deleting
    for item in runs_dir.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Enlace simbólico en datos: {item}; no se purga")

    shutil.rmtree(runs_dir)

    return {
        "result": "PURGED",
        "deleted_runs": run_dirs,
        "message": f"Purgados {len(run_dirs)} runs de {runs_dir}",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    p_install = sub.add_parser("install", help="Crear run de generación")
    p_install.add_argument("--project", required=True,
                           help="Ruta absoluta al proyecto")
    p_install.add_argument("--workspace", default=None,
                           help="Ruta al workspace externo (default: hermano del proyecto)")
    p_install.add_argument("--no-dispatch", action="store_true",
                           help="Solo preparar el run; no despachar Creator "
                                "(la supervisión puede durar hasta el presupuesto)")
    p_install.add_argument("--launch-dsh", action="store_true",
                           help="Arrancar 'dsh web' como hijo si no hay sesión autenticada")
    p_install.add_argument("--no-finalize", action="store_true",
                           help="No encadenar aceptación Host ni activación tras Creator")

    # accept
    p_accept = sub.add_parser("accept",
                              help="Solicitar validación Host de paquete generado")
    p_accept.add_argument("--workspace", required=True)
    p_accept.add_argument("--generated", required=True,
                          help="Ruta a creator-runs/<id>/generated")

    # verify-acceptance
    p_verify = sub.add_parser("verify-acceptance",
                              help="Verificar estado de aceptación de una generación")
    p_verify.add_argument("--workspace", required=True)
    p_verify.add_argument("--generation-id", default=None,
                          help="ID de generación opcional (default: activa o última)")

    # finalize
    p_finalize = sub.add_parser(
        "finalize", help="Ejecutar aceptación Host y activar si el veredicto es ACTIVE")
    p_finalize.add_argument("--workspace", required=True)
    p_finalize.add_argument("--generation-id", default=None,
                            help="ID de generación opcional (default: activa o última)")

    # update
    p_update = sub.add_parser("update", help="Regenerar sobre base cambiada")
    p_update.add_argument("--project", required=True)
    p_update.add_argument("--workspace", default=None)

    # uninstall
    p_uninstall = sub.add_parser("uninstall",
                                 help="Retirar modos/skills gestionados")
    p_uninstall.add_argument("--project", required=True)
    p_uninstall.add_argument("--workspace", default=None)

    # purge-data
    p_purge = sub.add_parser("purge-data",
                             help="Eliminar datos de runs (destructivo)")
    p_purge.add_argument("--workspace", required=True)
    p_purge.add_argument("--confirm", action="store_true",
                         help="Confirmar la eliminación destructiva")

    args = parser.parse_args()

    try:
        if args.command == "install":
            project = Path(args.project).resolve()
            workspace = (
                Path(args.workspace).resolve() if args.workspace
                else project.parent / f"{project.name}-workspace"
            )
            result = install(project, workspace,
                             dispatch_creator=not args.no_dispatch,
                             launch_dsh=args.launch_dsh,
                             finalize_host=not args.no_finalize)

        elif args.command == "accept":
            result = accept(Path(args.workspace).resolve(),
                            Path(args.generated).resolve())

        elif args.command == "verify-acceptance":
            result = verify_acceptance(
                Path(args.workspace).resolve(),
                generation_id=args.generation_id,
            )

        elif args.command == "finalize":
            result = finalize(
                Path(args.workspace).resolve(),
                generation_id=args.generation_id,
            )

        elif args.command == "update":
            project = Path(args.project).resolve()
            workspace = (
                Path(args.workspace).resolve() if args.workspace
                else project.parent / f"{project.name}-workspace"
            )
            result = update(project, workspace)

        elif args.command == "uninstall":
            project = Path(args.project).resolve()
            workspace = (
                Path(args.workspace).resolve() if args.workspace
                else project.parent / f"{project.name}-workspace"
            )
            result = uninstall(project, workspace)

        elif args.command == "purge-data":
            result = purge_data(
                Path(args.workspace).resolve(),
                confirm=args.confirm,
            )

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
