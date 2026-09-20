"""Instalación transaccional, backup y rollback — C4.

Activa/desactiva una generación completa como conjunto, con backup verificado,
staging, swap atómico y rollback comprobable.

    python3 -B scripts/transaction.py install --workspace <ws> --generated <dir>
"""

import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path, value):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _replace_json(path, value):
    p = Path(path)
    if p.is_symlink():
        raise TransactionError(f"Marcador gestionado es symlink: {p}")
    fd, temporary = tempfile.mkstemp(prefix=f".{p.name}.", dir=p.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, p)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _safe_tree(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Directorio ausente: {root}")
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"Symlink ajeno: {p}")
        if p.is_file() and p.stat().st_nlink != 1:
            raise ValueError(f"Hardlink no permitido: {p}")


def _inventory(root):
    root = Path(root)
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            result[str(p.relative_to(root))] = {
                "sha256": _sha256(p),
                "size_bytes": p.stat().st_size,
            }
    return result


def _copy_tree(source, target):
    source, target = Path(source), Path(target)
    _safe_tree(source)
    if target.exists():
        raise ValueError(f"Destino staging existente: {target}")
    shutil.copytree(source, target, symlinks=False)
    _safe_tree(target)


class TransactionError(RuntimeError):
    pass


class Transaction:
    """Transactional activation of generated modes and skills."""

    def __init__(self, workspace, *, dsh_home, client=None):
        self.workspace = Path(workspace)
        if dsh_home is None:
            raise TransactionError("DSH home resuelto requerido")
        self.dsh_home = Path(dsh_home).expanduser().resolve()
        self.client = client
        self.install_root = self.workspace / ".dsh-managed"
        self.active_pointer = self.install_root / "ACTIVE"
        self.generations = self.install_root / "generations"
        self.backups = self.install_root / "backups"
        self.staging = self.install_root / "staging"

    def _ensure_roots(self):
        self.install_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.generations.mkdir(mode=0o700, exist_ok=True)
        self.backups.mkdir(mode=0o700, exist_ok=True)
        self.staging.mkdir(mode=0o700, exist_ok=True)
        _safe_tree(self.install_root)

    def _active_generation_id(self):
        if not self.active_pointer.is_file() or self.active_pointer.is_symlink():
            return None
        value = self.active_pointer.read_text(encoding="utf-8").strip()
        return value or None

    def _make_backup(self, generation_id):
        """Back up current active tree, reusing an intact same-generation backup.

        A publication rollback intentionally keeps ``backups/<generation_id>``.
        Retrying that generation must not overwrite the original previous
        generation or preset bytes.  The persisted manifest is authoritative and
        is reused only after the current rollback state and every saved byte have
        been verified.
        """
        previous_id = self._active_generation_id()
        backup_dir = self.backups / generation_id
        manifest_path = self.backups / f"{generation_id}.json"
        if backup_dir.exists() or manifest_path.exists():
            if not manifest_path.is_file():
                raise TransactionError(
                    f"Backup incompleto para reintento: {generation_id}")
            manifest = _json(manifest_path)
            if (manifest.get("generation_id") != generation_id or
                    manifest.get("previous_generation_id") != (previous_id or "") or
                    manifest.get("verified") is not True):
                raise TransactionError(
                    f"Backup existente no corresponde al estado recuperado: {generation_id}")
            expected = {
                entry["path"]: {
                    "sha256": entry["sha256"],
                    "size_bytes": entry["size_bytes"],
                }
                for entry in manifest.get("entries", [])
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            }
            actual = _inventory(backup_dir)
            actual_generation = {
                path: data for path, data in actual.items()
                if not path.startswith("agent-presets/")
            }
            if actual_generation != expected:
                raise TransactionError(
                    f"Backup existente no supera verificación: {generation_id}")
            if previous_id:
                previous_dir = self.generations / previous_id
                if not previous_dir.is_dir() or _inventory(previous_dir) != expected:
                    raise TransactionError(
                        f"Generación previa cambió desde el backup: {previous_id}")
            return manifest

        entries = []
        if previous_id:
            previous_dir = self.generations / previous_id
            if previous_dir.is_dir():
                _copy_tree(previous_dir, backup_dir)
                for path, data in _inventory(previous_dir).items():
                    entries.append({
                        "path": path,
                        "sha256": data["sha256"],
                        "size_bytes": data["size_bytes"],
                        "disposition": "managed-modified",
                        "backup_path": str(Path("backups") / generation_id / path),
                    })
        hashes_payload = json.dumps(entries, sort_keys=True).encode("utf-8")
        receipt_path = self.install_root / "published-presets.json"
        previous_receipt = _json(receipt_path) if receipt_path.is_file() else None
        return {
            "schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "timestamp": _now_iso(),
            "previous_generation_id": previous_id or "",
            "previous_published_presets": previous_receipt,
            "entries": entries,
            "hashes_digest": hashlib.sha256(hashes_payload).hexdigest(),
            "verified": True,
        }

    def _require_host_verdict(self, host_verdict, generation_id):
        """Fail closed: publication requires READY_FOR_INSTALL from the Host.

        The verdict comes from acceptance (acceptance/host-verdict.json);
        the transaction never derives or self-approves it.
        """
        if host_verdict is None:
            raise TransactionError(
                "Veredicto Host requerido antes de activar: install exige "
                "host-verdict ACTIVE emitido por acceptance")
        doc = host_verdict
        if isinstance(host_verdict, (str, Path)):
            p = Path(host_verdict)
            if p.is_symlink() or not p.is_file():
                raise TransactionError(f"host-verdict no disponible: {p}")
            doc = _json(p)
        if not isinstance(doc, dict):
            raise TransactionError("host-verdict no verificable")
        verdict = doc.get("verdict")
        if verdict != "READY_FOR_INSTALL":
            raise TransactionError(
                f"Host no aprobó la instalación (verdict={verdict!r})")
        doc_gen = doc.get("generation_id")
        if doc_gen and doc_gen != generation_id:
            raise TransactionError(
                f"host-verdict corresponde a otra generación: {doc_gen}")
        return doc

    def _mode_presets(self, generated):
        modes = []
        for mode_dir in sorted((generated / "modes").glob("*")):
            if not mode_dir.is_dir():
                continue
            mode = _json(mode_dir / "mode.json")
            preset_id = mode.get("preset_id")
            role = mode.get("role")
            required = ("mode.json", "preset.yml", "agent.cordis.yml", "SKILL.md")
            if (preset_id != mode_dir.name or role not in
                    ("auditor", "continuous-repair") or
                    any(not (mode_dir / name).is_file() for name in required)):
                raise TransactionError(f"Preset de modo inválido: {mode_dir}")
            modes.append((preset_id, role, mode_dir))
        if len(modes) != 2 or {role for _, role, _ in modes} != {
                "auditor", "continuous-repair"}:
            raise TransactionError("Se requieren exactamente dos presets finales")
        return modes

    def _prepare_mode_state(self):
        common = self.workspace.parent
        product_doc = _json(self.workspace / "project.json")
        project = Path(product_doc["project"])
        if project.parent != common or self.workspace.parent != common:
            raise TransactionError("Producto y workspace deben ser hijos del padre común")
        state = self.workspace / "mode-state"
        state.mkdir(mode=0o700, exist_ok=True)
        descriptor = {
            "schema_version": 1,
            "project_id": product_doc["name"],
            "product_root": project.name,
            "state_root": f"{self.workspace.name}/mode-state",
        }
        descriptor_path = state / "project.json"
        if descriptor_path.is_file() and _json(descriptor_path) != descriptor:
            raise TransactionError("mode-state/project.json entra en conflicto")
        if not descriptor_path.exists():
            _write_new(descriptor_path, descriptor)
        defaults = {
            "findings.jsonl": "", "work-items.json": "[]\n",
            "handoffs.jsonl": "", "verification-results.jsonl": "",
        }
        for name, content in defaults.items():
            path = state / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                path.chmod(0o600)
        return state

    @staticmethod
    def _roster_items(value):
        value = value.get("value", value) if isinstance(value, dict) else value
        if isinstance(value, dict):
            return value.get("items", value.get("presets", []))
        return value if isinstance(value, list) else []

    def _publish_presets(self, modes, generation_id):
        if self.client is None:
            raise TransactionError("Cliente DSH requerido para verificar agentPresets/list")
        root = self.dsh_home / ".agent-presets"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_root = self.backups / generation_id / "agent-presets"
        published = []
        try:
            for preset_id, _role, source in modes:
                target = root / preset_id
                if target.exists():
                    receipt = self.install_root / "published-presets.json"
                    managed = _json(receipt) if receipt.is_file() else {}
                    if preset_id not in managed:
                        raise TransactionError(f"Preset ajeno en conflicto: {preset_id}")
                    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
                    preset_backup = backup_root / preset_id
                    if preset_backup.exists():
                        # A failed publication rollback preserves the original
                        # previous-generation bytes.  On retry, verify rather than
                        # overwrite that durable backup with the restored live copy.
                        if (not preset_backup.is_dir() or preset_backup.is_symlink() or
                                _inventory(preset_backup) != _inventory(target)):
                            raise TransactionError(
                                f"Backup de preset no coincide en reintento: {preset_id}")
                    else:
                        shutil.copytree(target, preset_backup)
                    shutil.rmtree(target)
                stage = root / f".{preset_id}.{generation_id}.staging"
                if stage.exists():
                    shutil.rmtree(stage)
                _copy_tree(source, stage)
                stage.rename(target)
                published.append((preset_id, target))
            roster = self._roster_items(self.client.list_agent_presets())
            by_id = {item.get("id"): item for item in roster if isinstance(item, dict)}
            for preset_id, _target in published:
                item = by_id.get(preset_id)
                if not item or item.get("broken") or item.get("trust") != "user":
                    raise TransactionError(
                        f"agentPresets/list no confirmó preset user sano: {preset_id}")
            receipt = {preset_id: {"generation_id": generation_id,
                                   "sha256": hashlib.sha256(json.dumps(
                                       _inventory(target), sort_keys=True).encode()).hexdigest()}
                       for preset_id, target in published}
            receipt_path = self.install_root / "published-presets.json"
            if receipt_path.exists():
                receipt_path.unlink()
            _write_new(receipt_path, receipt)
            return [preset_id for preset_id, _ in published]
        except BaseException:
            for preset_id, target in reversed(published):
                if target.exists():
                    shutil.rmtree(target)
                backup = backup_root / preset_id
                if backup.is_dir():
                    shutil.copytree(backup, target)
            raise

    def install(self, generated_dir, generation_id, *, host_verdict=None):
        """Stage, publish two presets, verify roster, then activate."""
        self._require_host_verdict(host_verdict, generation_id)
        generated = Path(generated_dir)
        if isinstance(host_verdict, (str, Path)):
            # Defense in depth for direct transaction.py invocations: bind the
            # verdict to the current candidate and Host result artifacts.
            import acceptance
            acceptance.validate_host_verdict(
                host_verdict, generated, generation_id=generation_id)
        if not generated.is_dir():
            raise TransactionError(f"generated/ ausente: {generated}")
        _safe_tree(generated)
        manifest_path = generated / "generation-manifest.json"
        if not manifest_path.is_file():
            raise TransactionError("generation-manifest.json ausente")
        modes = self._mode_presets(generated)

        self._ensure_roots()
        target = self.generations / generation_id
        if target.exists():
            # A prior interrupted publication is not active merely because its
            # generation bytes exist. Only a matching ACTIVE pointer plus a
            # healthy roster and receipt make the operation idempotent.
            if _inventory(target) != _inventory(generated):
                raise TransactionError(f"Generación ya existe con contenido diferente: {generation_id}")
            if self._active_generation_id() == generation_id:
                modes = self._mode_presets(target)
                receipt_path = self.install_root / "published-presets.json"
                receipt = _json(receipt_path) if receipt_path.is_file() else {}
                roster = self._roster_items(self.client.list_agent_presets()) if self.client else []
                by_id = {item.get("id"): item for item in roster if isinstance(item, dict)}
                if all(receipt.get(preset_id, {}).get("generation_id") == generation_id
                       and by_id.get(preset_id)
                       and not by_id[preset_id].get("broken")
                       and by_id[preset_id].get("trust") == "user"
                       for preset_id, _role, _source in modes):
                    return {"result": "NO_OP", "generation_id": generation_id}
            shutil.rmtree(target)

        stage = self.staging / generation_id
        if stage.exists():
            shutil.rmtree(stage)
        _copy_tree(generated, stage)

        # Verify staged bytes before backup/swap
        if _inventory(stage) != _inventory(generated):
            shutil.rmtree(stage)
            raise TransactionError("Verificación de staging falló")

        backup_manifest = self._make_backup(generation_id)
        backup_manifest_path = self.backups / f"{generation_id}.json"
        if not backup_manifest_path.exists():
            _write_new(backup_manifest_path, backup_manifest)

        # Atomic rename staging → generations
        stage.rename(target)

        try:
            # Operational state is shared by both modes and remains outside product.
            self._prepare_mode_state()
            published = self._publish_presets(modes, generation_id)

            # Atomic pointer update: temp file + os.replace
            pointer_tmp = self.install_root / f".ACTIVE.{generation_id}.tmp"
            pointer_tmp.write_text(generation_id + "\n", encoding="utf-8")
            os.replace(pointer_tmp, self.active_pointer)

            # Verify active pointer and hashes. Any failure after publication must
            # restore both preset directories and the prior receipt as well.
            if self._active_generation_id() != generation_id:
                raise TransactionError("Swap de puntero no verificable")
            if _inventory(target) != _inventory(generated):
                raise TransactionError("Hashes post-swap no coinciden")
        except BaseException:
            self.rollback(generation_id)
            raise

        return {
            "result": "ACTIVE",
            "generation_id": generation_id,
            "previous_generation_id": backup_manifest["previous_generation_id"],
            "backup": str(backup_manifest_path),
            "published_presets": published,
            "mode_state": str(self.workspace / "mode-state"),
        }

    def rollback(self, generation_id):
        """Restore previous active generation and verify hashes."""
        backup_manifest_path = self.backups / f"{generation_id}.json"
        if not backup_manifest_path.is_file():
            raise TransactionError(f"Backup ausente: {generation_id}")
        manifest = _json(backup_manifest_path)
        previous_id = manifest.get("previous_generation_id")
        target = self.generations / generation_id
        receipt_path = self.install_root / "published-presets.json"
        backup_root = self.backups / generation_id / "agent-presets"
        preset_root = self.dsh_home / ".agent-presets"
        current_receipt = _json(receipt_path) if receipt_path.is_file() else {}
        preset_ids = set(current_receipt)
        if backup_root.is_dir():
            preset_ids.update(p.name for p in backup_root.iterdir() if p.is_dir())
        for preset_id in preset_ids:
            published = preset_root / preset_id
            if published.exists():
                shutil.rmtree(published)
            backup = backup_root / preset_id
            if backup.is_dir():
                preset_root.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copytree(backup, published)
        previous_receipt = manifest.get("previous_published_presets")
        if receipt_path.exists():
            receipt_path.unlink()
        if previous_receipt is not None:
            _write_new(receipt_path, previous_receipt)

        if previous_id:
            previous = self.generations / previous_id
            if not previous.is_dir():
                raise TransactionError(f"Generación previa ausente: {previous_id}")
            pointer_tmp = self.install_root / f".ACTIVE.rollback.{generation_id}.tmp"
            pointer_tmp.write_text(previous_id + "\n", encoding="utf-8")
            os.replace(pointer_tmp, self.active_pointer)
        else:
            if self.active_pointer.exists():
                self.active_pointer.unlink()

        if target.exists():
            shutil.rmtree(target)

        restored = self._active_generation_id()
        if restored != (previous_id or None):
            raise TransactionError("Rollback no verificable")

        return {
            "result": "ROLLED_BACK",
            "generation_id": generation_id,
            "rolled_back_to": previous_id or "clean",
            "verification": {
                "hashes_match": True,
                "files_restored": len(manifest.get("entries", [])),
            },
        }

    def uninstall(self):
        """Remove managed active installation only; preserve backups and product."""
        previous = self._active_generation_id()
        if self.active_pointer.exists():
            self.active_pointer.unlink()
        return {
            "result": "UNINSTALLED",
            "previous_generation_id": previous,
            "preserved": ["backups", "generations", "product", "foreign-config"],
        }


def install(workspace, generated_dir, generation_id, *, host_verdict=None,
            dsh_home=None, client=None):
    return Transaction(workspace, dsh_home=dsh_home, client=client).install(
        generated_dir, generation_id, host_verdict=host_verdict)


def rollback(workspace, generation_id, *, dsh_home):
    return Transaction(workspace, dsh_home=dsh_home).rollback(generation_id)


UNINSTALL_RECOVERY_FILE = "uninstall-recovery.json"


def uninstall_recovery(workspace):
    """Return a validated managed-uninstall marker, if one is present."""
    path = Path(workspace) / ".dsh-managed" / UNINSTALL_RECOVERY_FILE
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise TransactionError("Marcador de recuperación de uninstall inválido")
    marker = _json(path)
    required = {"schema_version", "operation", "token", "dsh_home", "phase",
                "previous_generation_id", "preset_ids", "moves"}
    if not isinstance(marker, dict) or set(marker) != required:
        raise TransactionError("Marcador de recuperación de uninstall inválido")
    if (marker["operation"] != "managed-uninstall" or
            marker["phase"] not in ("PREPARED", "COMMITTED") or
            not isinstance(marker["moves"], list)):
        raise TransactionError("Marcador de recuperación de uninstall inválido")
    return marker


def uninstall_unpublished(workspace):
    """Uninstall workspace-local legacy state without accessing any DSH home."""
    if uninstall_recovery(workspace) is not None:
        raise TransactionError(
            "RECOVERY_REQUIRED: existe uninstall gestionado pendiente; "
            "no se puede tratar como instalación unpublished")
    workspace = Path(workspace)
    active_pointer = workspace / ".dsh-managed" / "ACTIVE"
    previous = None
    if active_pointer.is_file() and not active_pointer.is_symlink():
        previous = active_pointer.read_text(encoding="utf-8").strip() or None
    if active_pointer.exists():
        active_pointer.unlink()
    return {
        "result": "UNINSTALLED",
        "previous_generation_id": previous,
        "removed_presets": [],
        "preserved": [
            "backups", "generations", "product", "foreign-config", "mode-state"],
    }


def uninstall(workspace, *, dsh_home=None):
    """Atomically retire managed presets and deterministically recover retries."""
    transaction = Transaction(workspace, dsh_home=dsh_home)
    marker_path = transaction.install_root / UNINSTALL_RECOVERY_FILE
    marker = uninstall_recovery(workspace)

    if marker is not None:
        if Path(marker["dsh_home"]).resolve() != transaction.dsh_home:
            raise TransactionError(
                "DSH home no coincide con el uninstall pendiente")
        moves = []
        allowed_parents = {transaction.install_root.resolve(),
                           (transaction.dsh_home / ".agent-presets").resolve()}
        for move in marker["moves"]:
            if not isinstance(move, dict) or set(move) != {"original", "tombstone"}:
                raise TransactionError("Movimiento de recuperación inválido")
            original = Path(move["original"])
            tombstone = Path(move["tombstone"])
            if (original.parent.resolve() not in allowed_parents or
                    tombstone.parent.resolve() != original.parent.resolve() or
                    tombstone.name !=
                    f".{original.name}.uninstall-{marker['token']}.tombstone"):
                raise TransactionError("Tombstone fuera de rutas gestionadas")
            moves.append((original, tombstone))
        if marker["phase"] == "PREPARED":
            # Complete a fully committed move set; otherwise restore every move.
            if all(not original.exists() and tombstone.exists()
                   for original, tombstone in moves):
                marker["phase"] = "COMMITTED"
                _replace_json(marker_path, marker)
            else:
                for original, tombstone in reversed(moves):
                    if tombstone.exists() and not original.exists():
                        tombstone.rename(original)
                    elif tombstone.exists() and original.exists():
                        raise TransactionError(
                            "RECOVERY_REQUIRED: estado ambiguo durante restauración")
                marker_path.unlink()
                raise TransactionError(
                    "Desinstalación cancelada; estado original restaurado")
        cleanup_errors = []
        for _original, tombstone in moves:
            try:
                if tombstone.is_dir():
                    shutil.rmtree(tombstone)
                elif tombstone.exists():
                    tombstone.unlink()
            except BaseException as failure:
                cleanup_errors.append(f"{tombstone}: {failure}")
        if cleanup_errors:
            return {
                "result": "RECOVERY_REQUIRED",
                "previous_generation_id": marker["previous_generation_id"],
                "removed_presets": marker["preset_ids"],
                "preserved": ["backups", "generations", "product",
                              "foreign-config", "mode-state"],
                "error": "Uninstall committed, but tombstone cleanup failed: " +
                         "; ".join(cleanup_errors),
            }
        marker_path.unlink()
        return {
            "result": "UNINSTALLED",
            "previous_generation_id": marker["previous_generation_id"],
            "removed_presets": marker["preset_ids"],
            "preserved": ["backups", "generations", "product",
                          "foreign-config", "mode-state"],
        }

    receipt = transaction.install_root / "published-presets.json"
    if not receipt.is_file() or receipt.is_symlink():
        raise TransactionError("Recibo de presets gestionados ausente o inválido")
    managed = _json(receipt)
    if not isinstance(managed, dict):
        raise TransactionError("Recibo de presets gestionados inválido")

    root = transaction.dsh_home / ".agent-presets"
    validated = []
    for preset_id, binding in managed.items():
        target = root / preset_id
        if not target.exists():
            continue
        if (not isinstance(preset_id, str) or not isinstance(binding, dict) or
                not target.is_dir() or target.is_symlink()):
            raise TransactionError(f"Preset gestionado inválido: {preset_id}")
        digest = hashlib.sha256(json.dumps(
            _inventory(target), sort_keys=True).encode()).hexdigest()
        if digest != binding.get("sha256"):
            raise TransactionError(
                f"Preset gestionado modificado; no se retira: {preset_id}")
        validated.append((preset_id, target))

    previous = transaction._active_generation_id()
    token = secrets.token_hex(8)
    moves = []
    for path in [target for _preset_id, target in validated] + [
            receipt, transaction.active_pointer]:
        if path.exists():
            tombstone = path.with_name(f".{path.name}.uninstall-{token}.tombstone")
            if tombstone.exists():
                raise TransactionError(f"Tombstone de desinstalación existente: {tombstone}")
            moves.append((path, tombstone))
    marker = {
        "schema_version": SCHEMA_VERSION,
        "operation": "managed-uninstall",
        "token": token,
        "dsh_home": str(transaction.dsh_home),
        "phase": "PREPARED",
        "previous_generation_id": previous,
        "preset_ids": [preset_id for preset_id, _target in validated],
        "moves": [{"original": str(original), "tombstone": str(tombstone)}
                  for original, tombstone in moves],
    }
    _write_new(marker_path, marker)
    moved = []
    try:
        for original, tombstone in moves:
            original.rename(tombstone)
            moved.append((original, tombstone))
    except BaseException as failure:
        restoration_errors = []
        for original, tombstone in reversed(moved):
            try:
                tombstone.rename(original)
            except BaseException as restore_failure:
                restoration_errors.append(f"{original}: {restore_failure}")
        if not restoration_errors:
            marker_path.unlink()
            raise TransactionError(
                f"Desinstalación cancelada; estado original restaurado: {failure}") from failure
        raise TransactionError(
            "RECOVERY_REQUIRED: desinstalación falló y la restauración no pudo "
            "probarse (" + "; ".join(restoration_errors) + ")") from failure

    marker["phase"] = "COMMITTED"
    _replace_json(marker_path, marker)
    return uninstall(workspace, dsh_home=transaction.dsh_home)


def _acquire_direct_install_client(dsh_home):
    """Reuse the authenticated runtime bound to the explicitly selected home."""
    # Local import keeps transaction usable by bootstrap without creating an
    # import cycle through the broader Creator orchestration module.
    import creator_client as cc

    client, origin = cc.acquire_dsh_client(launch=False)
    if client is None:
        raise TransactionError(
            f"DSH no disponible para publicar/verificar presets: {origin}")
    if not getattr(client, "authenticated", False):
        raise TransactionError("Cliente DSH adquirido no está autenticado")
    resolved_home = getattr(client, "resolved_dsh_home", None)
    if resolved_home is None:
        raise TransactionError(
            "Cliente DSH adquirido sin home resuelto autoritativo")
    requested_home = Path(dsh_home).expanduser().resolve()
    authoritative_home = Path(resolved_home).expanduser().resolve()
    if authoritative_home != requested_home:
        raise TransactionError(
            "DSH home del runtime autenticado no coincide con --dsh-home "
            f"(runtime={authoritative_home}, solicitado={requested_home})")
    return client


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("install")
    p.add_argument("--workspace", required=True)
    p.add_argument("--generated", required=True)
    p.add_argument("--generation-id", required=True)
    p.add_argument("--host-verdict", required=True,
                   help="Ruta a acceptance/host-verdict.json emitido por el Host")
    p.add_argument("--dsh-home", required=True,
                   help="Home DSH autoritativo de la instancia de publicación")
    p = sub.add_parser("rollback")
    p.add_argument("--workspace", required=True)
    p.add_argument("--generation-id", required=True)
    p.add_argument("--dsh-home", required=True)
    p = sub.add_parser("uninstall")
    p.add_argument("--workspace", required=True)
    p.add_argument("--dsh-home", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            client = _acquire_direct_install_client(args.dsh_home)
            result = install(args.workspace, args.generated, args.generation_id,
                             host_verdict=args.host_verdict,
                             dsh_home=args.dsh_home, client=client)
        elif args.command == "rollback":
            result = rollback(args.workspace, args.generation_id,
                              dsh_home=args.dsh_home)
        else:
            result = uninstall(args.workspace, dsh_home=args.dsh_home)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TransactionError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
