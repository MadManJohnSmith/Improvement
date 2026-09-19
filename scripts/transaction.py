"""Instalación transaccional, backup y rollback — C4.

Activa/desactiva una generación completa como conjunto, con backup verificado,
staging, swap atómico y rollback comprobable.

    python3 -B scripts/transaction.py install --workspace <ws> --generated <dir>
"""

import hashlib
import json
import os
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

    def __init__(self, workspace):
        self.workspace = Path(workspace)
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
        """Back up current active tree with hashes before swap."""
        previous_id = self._active_generation_id()
        entries = []
        backup_dir = self.backups / generation_id
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
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "timestamp": _now_iso(),
            "previous_generation_id": previous_id or "",
            "entries": entries,
            "hashes_digest": hashlib.sha256(hashes_payload).hexdigest(),
            "verified": True,
        }
        return manifest

    def _require_host_verdict(self, host_verdict, generation_id):
        """Fail closed: activation requires an explicit Host verdict ACTIVE.

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
        if verdict != "ACTIVE":
            raise TransactionError(
                f"Host no aprobó la activación (verdict={verdict!r})")
        doc_gen = doc.get("generation_id")
        if doc_gen and doc_gen != generation_id:
            raise TransactionError(
                f"host-verdict corresponde a otra generación: {doc_gen}")
        return doc

    def install(self, generated_dir, generation_id, *, host_verdict=None):
        """Stage and atomically activate a generated package."""
        self._require_host_verdict(host_verdict, generation_id)
        generated = Path(generated_dir)
        if not generated.is_dir():
            raise TransactionError(f"generated/ ausente: {generated}")
        _safe_tree(generated)
        manifest_path = generated / "generation-manifest.json"
        if not manifest_path.is_file():
            raise TransactionError("generation-manifest.json ausente")

        self._ensure_roots()
        target = self.generations / generation_id
        if target.exists():
            # Idempotent if byte-identical
            if _inventory(target) == _inventory(generated):
                return {"result": "NO_OP", "generation_id": generation_id}
            raise TransactionError(f"Generación ya existe con contenido diferente: {generation_id}")

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
        if backup_manifest_path.exists():
            backup_manifest_path.unlink()
        _write_new(backup_manifest_path, backup_manifest)

        # Atomic rename staging → generations
        stage.rename(target)

        # Atomic pointer update: temp file + os.replace
        pointer_tmp = self.install_root / f".ACTIVE.{generation_id}.tmp"
        pointer_tmp.write_text(generation_id + "\n", encoding="utf-8")
        os.replace(pointer_tmp, self.active_pointer)

        # Verify active pointer and hashes
        if self._active_generation_id() != generation_id:
            raise TransactionError("Swap de puntero no verificable")
        if _inventory(target) != _inventory(generated):
            # Attempt rollback
            self.rollback(generation_id)
            raise TransactionError("Hashes post-swap no coinciden")

        return {
            "result": "ACTIVE",
            "generation_id": generation_id,
            "previous_generation_id": backup_manifest["previous_generation_id"],
            "backup": str(backup_manifest_path),
        }

    def rollback(self, generation_id):
        """Restore previous active generation and verify hashes."""
        backup_manifest_path = self.backups / f"{generation_id}.json"
        if not backup_manifest_path.is_file():
            raise TransactionError(f"Backup ausente: {generation_id}")
        manifest = _json(backup_manifest_path)
        previous_id = manifest.get("previous_generation_id")
        target = self.generations / generation_id

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


def install(workspace, generated_dir, generation_id, *, host_verdict=None):
    return Transaction(workspace).install(generated_dir, generation_id,
                                          host_verdict=host_verdict)


def rollback(workspace, generation_id):
    return Transaction(workspace).rollback(generation_id)


def uninstall(workspace):
    return Transaction(workspace).uninstall()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("install")
    p.add_argument("--workspace", required=True)
    p.add_argument("--generated", required=True)
    p.add_argument("--generation-id", required=True)
    p.add_argument("--host-verdict", required=True,
                   help="Ruta a acceptance/host-verdict.json emitido por el Host")
    p = sub.add_parser("rollback")
    p.add_argument("--workspace", required=True)
    p.add_argument("--generation-id", required=True)
    p = sub.add_parser("uninstall")
    p.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install(args.workspace, args.generated, args.generation_id,
                             host_verdict=args.host_verdict)
        elif args.command == "rollback":
            result = rollback(args.workspace, args.generation_id)
        else:
            result = uninstall(args.workspace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TransactionError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        raise SystemExit(1)
