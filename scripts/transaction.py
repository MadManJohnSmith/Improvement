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
import re
from datetime import datetime, timezone
from pathlib import Path

from composition_contract import validate_operational_composition
from layout_contract import layout_from_paths, validate_mode_layout
from mode_lifecycle import initialize_state

FRAMEWORK = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


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
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Directorio ausente o peligroso: {root}")
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"Symlink ajeno: {p}")
        if not p.is_dir() and not p.is_file():
            raise ValueError(f"Entrada no regular: {p}")
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
        modes_root = generated / "modes"
        if not modes_root.is_dir() or modes_root.is_symlink():
            raise TransactionError("generated/modes debe ser un directorio regular")
        modes = []
        for mode_dir in sorted(modes_root.iterdir()):
            if not mode_dir.is_dir() or mode_dir.is_symlink():
                raise TransactionError(f"Entrada de modo peligrosa: {mode_dir}")
            try:
                mode = _json(mode_dir / "mode.json")
            except (OSError, ValueError) as error:
                raise TransactionError(f"Preset de modo inválido: {mode_dir}") from error
            preset_id = mode.get("preset_id")
            role = mode.get("role")
            required = ("mode.json", "preset.yml", "agent.cordis.yml", "SKILL.md")
            if (preset_id != mode_dir.name or not SAFE_NAME.fullmatch(
                    preset_id or "") or role not in
                    ("auditor", "continuous-repair") or
                    any(not (mode_dir / name).is_file() or
                        (mode_dir / name).is_symlink() for name in required)):
                raise TransactionError(f"Preset de modo inválido: {mode_dir}")
            product = Path(_json(self.workspace / "project.json")["project"])
            try:
                validate_mode_layout(
                    mode_dir, layout_from_paths(product, self.workspace))
                validate_operational_composition(mode_dir / "agent.cordis.yml")
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise TransactionError(
                    f"Contrato de modo inválido: {mode_dir}: {error}") from error
            modes.append((preset_id, role, mode_dir))
        if (len(modes) != 2 or len({preset_id for preset_id, _, _ in modes}) != 2 or
                {role for _, role, _ in modes} != {
                    "auditor", "continuous-repair"}):
            raise TransactionError("Se requieren exactamente dos presets finales")
        return modes

    def _prepare_mode_state(self):
        common = self.workspace.parent
        product_doc = _json(self.workspace / "project.json")
        project = Path(product_doc["project"])
        if project.parent != common or self.workspace.parent != common:
            raise TransactionError("Producto y workspace deben ser hijos del padre común")
        state = self.workspace / "mode-state"
        layout = layout_from_paths(project, self.workspace)
        descriptor = {
            "schema_version": 1,
            "project_id": product_doc["name"],
            "product_root": layout["product_root"],
            "state_root": layout["state_root"],
        }
        try:
            return initialize_state(
                state, descriptor,
                self.install_root / "mode-state-legacy")
        except (OSError, ValueError) as error:
            raise TransactionError(f"mode-state inválido: {error}") from error

    @staticmethod
    def _roster_items(value):
        value = value.get("value", value) if isinstance(value, dict) else value
        if isinstance(value, dict):
            return value.get("items", value.get("presets", []))
        return value if isinstance(value, list) else []

    @staticmethod
    def _rpc_value(value):
        return value.get("value", value) if isinstance(value, dict) else value

    def _active_presets_match(self, modes, skill_root):
        """Prove the running declarations came from this generation's bundle."""
        if not hasattr(self.client, "read_agent_preset"):
            return False
        expected_root = str(skill_root.resolve())
        for preset_id, _role, source in modes:
            try:
                document = self._rpc_value(self.client.read_agent_preset(preset_id))
            except Exception:
                return False
            if not isinstance(document, dict) or document.get("agentPreset") != preset_id:
                return False
            content = document.get("content")
            if not isinstance(content, str) or expected_root not in content:
                return False
            expected = validate_operational_composition(source / "agent.cordis.yml")
            actual = re.findall(
                r"(?m)^\s*-\s+id:\s*['\"]?([^'\"\s]+)['\"]?\s*$"
                r"\n\s+name:\s*['\"]?([^'\"\s]+)['\"]?\s*$",
                content)
            if actual != [(row["id"], row["name"]) for row in expected]:
                return False
        return True

    @staticmethod
    def _yaml_scalar(value):
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _composition_with_skill_root(source, skill_root):
        """Replace the generated skill provider with the bundle-local root."""
        try:
            rows = validate_operational_composition(source)
        except ValueError as error:
            raise TransactionError(
                f"Composición operativa inválida: {source}: {error}") from error
        result = []
        for row in rows:
            if row["name"] == "@deepseek-ai/dsh-skill-filesystem":
                result.extend([
                    f"- id: {row['id']}",
                    "  name: '@deepseek-ai/dsh-skill-filesystem'",
                    "  config:",
                    "    includeDefaultRoots: false",
                    "    customSkillDirs:",
                    f"      - {Transaction._yaml_scalar(skill_root.resolve())}",
                ])
            else:
                result.extend(row["lines"])
        return result

    def _bundle_skills(self, generated, modes, bundle):
        skill_root = bundle / "skills"
        skill_root.mkdir(mode=0o700)
        sources = []
        generated_skills = generated / "skills"
        if generated_skills.exists():
            if not generated_skills.is_dir() or generated_skills.is_symlink():
                raise TransactionError("generated/skills debe ser un directorio regular")
            for source in sorted(generated_skills.iterdir()):
                if (not source.is_dir() or source.is_symlink() or
                        not re.fullmatch(r"[a-z0-9][a-z0-9-]*", source.name)):
                    raise TransactionError(f"Entrada de skill peligrosa: {source}")
                sources.append((source.name, source))
        for preset_id, _role, mode_dir in modes:
            sources.append((preset_id, mode_dir))
        seen = set()
        for name, source in sources:
            if name in seen:
                raise TransactionError(f"Colisión de skill en bundle: {name}")
            seen.add(name)
            target = skill_root / name
            if source.name == name and source.parent.name == "skills":
                _copy_tree(source, target)
            else:
                _safe_tree(source)
                target.mkdir(mode=0o700)
                excluded = {"mode.json", "preset.yml", "agent.cordis.yml"}
                for item in source.iterdir():
                    if item.name in excluded:
                        continue
                    destination = target / item.name
                    if item.is_dir():
                        shutil.copytree(item, destination, symlinks=False)
                    elif item.is_file():
                        shutil.copy2(item, destination)
                    else:
                        raise TransactionError(f"Recurso de modo peligroso: {item}")
                _safe_tree(target)
            entrypoint = target / "SKILL.md"
            if (not entrypoint.is_file() or entrypoint.is_symlink() or
                    entrypoint.stat().st_nlink != 1):
                raise TransactionError(f"SKILL.md inseguro o ausente en bundle: {name}")
        return skill_root

    def _build_preset_bundle(self, generated, modes, generation_id):
        project_id = _json(self.workspace / "project.json")["name"]
        safe_project = re.sub(r"[^a-z0-9._-]+", "-", project_id.lower()).strip("-")
        bundle_name = f"@improvement/{safe_project}-presets"
        bundle = self.install_root / "bundles" / generation_id
        if bundle.exists():
            shutil.rmtree(bundle)
        bundle.mkdir(mode=0o700, parents=True)
        package = {
            "name": bundle_name,
            "version": "1.0.0",
            "private": True,
            "type": "module",
            "dsh": {"bundle": {"patch": "./cordis.patch.yml"}},
        }
        (bundle / "package.json").write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        skill_root = self._bundle_skills(generated, modes, bundle)
        rows = []
        for preset_id, _role, source in modes:
            metadata = {}
            for line in (source / "preset.yml").read_text(encoding="utf-8").splitlines():
                if ":" in line and not line.startswith((" ", "\t")):
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip().strip("'\"")
            try:
                order = int(metadata.get("order", "100"))
            except ValueError as exc:
                raise TransactionError(f"order inválido en preset {preset_id}") from exc
            plugins = self._composition_with_skill_root(
                source / "agent.cordis.yml", skill_root)
            rows.extend([
                "- insert:",
                f"    - id: preset-{preset_id}",
                "      name: '@deepseek-ai/dsh-agent-preset'",
                "      config:",
                f"        id: {self._yaml_scalar(preset_id)}",
                f"        name: {self._yaml_scalar(metadata.get('name', preset_id))}",
                f"        description: {self._yaml_scalar(metadata.get('description', ''))}",
                f"        order: {order}",
                "        plugins:",
                *["          " + line for line in plugins],
            ])
        (bundle / "cordis.patch.yml").write_text(
            "\n".join(rows) + "\n", encoding="utf-8")
        return bundle_name, bundle

    def _publish_presets(self, generated, modes, generation_id):
        if self.client is None:
            raise TransactionError("Cliente DSH requerido para verificar agentPresets/list")
        bundle_name, bundle = self._build_preset_bundle(
            generated, modes, generation_id)
        preset_ids = [preset_id for preset_id, _role, _source in modes]

        # A retry after relaunch first proves that DSH loaded this exact candidate.
        # Reinstalling the stable package name would itself report restart-required.
        already_active = self._active_presets_match(modes, bundle / "skills")
        if not already_active:
            outcome = self._rpc_value(self.client.install_bundle(bundle))
            application = outcome.get("application") if isinstance(outcome, dict) else None
            if application == "restart-required":
                return {"result": "RESTART_REQUIRED", "preset_ids": preset_ids}
            if application != "applied":
                raise TransactionError(
                    f"pluginManager/installBundle no aplicó el bundle: {application!r}")

        try:
            roster = self._roster_items(self.client.list_agent_presets())
            by_id = {item.get("id"): item for item in roster if isinstance(item, dict)}
            for preset_id in preset_ids:
                item = by_id.get(preset_id)
                if not item or item.get("broken") is True:
                    raise TransactionError(
                        f"agentPresets/list no confirmó preset sano: {preset_id}")
            if not self._active_presets_match(modes, bundle / "skills"):
                raise TransactionError(
                    "agentPresets/read no confirmó la composición activa candidata")
            receipt = {
                "schema_version": 2,
                "generation_id": generation_id,
                "bundle_name": bundle_name,
                "bundle_path": str(bundle),
                "sha256": hashlib.sha256(json.dumps(
                    _inventory(bundle), sort_keys=True).encode()).hexdigest(),
                "preset_ids": preset_ids,
            }
            receipt_path = self.install_root / "published-presets.json"
            if receipt_path.exists():
                receipt_path.unlink()
            _write_new(receipt_path, receipt)
            return {"result": "APPLIED", "preset_ids": preset_ids}
        except BaseException:
            if not already_active:
                try:
                    self.client.remove_bundle(bundle_name)
                except BaseException:
                    pass
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
                receipt_generation = receipt.get("generation_id")
                receipt_ids = set(receipt.get("preset_ids", []))
                receipt_bundle = Path(receipt.get("bundle_path", ""))
                expected_ids = [preset_id for preset_id, _role, _source in modes]
                if (receipt_generation == generation_id and
                        receipt_ids == set(expected_ids) and
                        all(by_id.get(preset_id)
                            and by_id[preset_id].get("broken") is not True
                            for preset_id in expected_ids) and
                        self._active_presets_match(
                            modes, receipt_bundle / "skills")):
                    return {"result": "NO_OP", "generation_id": generation_id,
                            "published_presets": expected_ids,
                            "mode_state": str(self.workspace / "mode-state")}
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

        # Atomic rename staging → generations, then re-validate the exact bytes
        # that publication will consume.
        stage.rename(target)
        modes = self._mode_presets(target)

        try:
            # Operational state is shared by both modes and remains outside product.
            self._prepare_mode_state()
            publication = self._publish_presets(target, modes, generation_id)
            if publication["result"] == "RESTART_REQUIRED":
                return {
                    "result": "RESTART_REQUIRED",
                    "generation_id": generation_id,
                    "previous_generation_id": backup_manifest["previous_generation_id"],
                    "message": (
                        "DSH guardó la actualización del bundle pero requiere "
                        "reinicio; relanza DSH y repite bootstrap install"),
                }
            published = publication["preset_ids"]
            expected_ids = [preset_id for preset_id, _role, _source in modes]
            if published != expected_ids:
                raise TransactionError(
                    "Publicación devolvió cardinalidad/orden de presets inconsistente")

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
        receipt_path = self.install_root / "published-presets.json"
        if receipt_path.is_file() and self.client is not None:
            receipt = _json(receipt_path)
            bundle_name = receipt.get("bundle_name")
            if bundle_name:
                try:
                    self.client.remove_bundle(bundle_name)
                except BaseException:
                    pass
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
            if (self.client is not None and
                    previous_receipt.get("schema_version") == 2 and
                    previous_receipt.get("bundle_path")):
                self.client.install_bundle(previous_receipt["bundle_path"])

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


def uninstall(workspace, *, dsh_home=None, client=None):
    """Retire the managed DSH bundle and preserve workspace history/state."""
    transaction = Transaction(workspace, dsh_home=dsh_home, client=client)
    marker_path = transaction.install_root / UNINSTALL_RECOVERY_FILE
    marker = uninstall_recovery(workspace)

    receipt = transaction.install_root / "published-presets.json"
    if marker is None and receipt.is_file():
        managed = _json(receipt)
        if managed.get("schema_version") == 2 and managed.get("bundle_name"):
            if transaction.client is None:
                transaction.client = _acquire_direct_install_client(
                    transaction.dsh_home)
            bundle_path = Path(managed.get("bundle_path", ""))
            if not bundle_path.is_dir() or bundle_path.is_symlink():
                raise TransactionError("Bundle gestionado ausente o inválido")
            digest = hashlib.sha256(json.dumps(
                _inventory(bundle_path), sort_keys=True).encode()).hexdigest()
            if digest != managed.get("sha256"):
                raise TransactionError("Bundle gestionado modificado; no se retira")
            transaction.client.remove_bundle(managed["bundle_name"])
            receipt.unlink()
            if transaction.active_pointer.exists():
                transaction.active_pointer.unlink()
            return {
                "result": "UNINSTALLED",
                "previous_generation_id": managed.get("generation_id"),
                "removed_presets": managed.get("preset_ids", []),
                "preserved": ["backups", "generations", "product",
                              "foreign-config", "mode-state"],
            }

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
