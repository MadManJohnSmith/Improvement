"""Tests de bootstrap determinista — C1.

Valida que install/accept/update/uninstall/purge-data funcionan correctamente.
Clone limpio + proveedor → un comando crea run completo; repetición es no-op;
producto y configuración global sin cambios; errores dejan checkpoint RETAINED.

    python3 -B -m unittest tests.test_bootstrap -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap as bs


class _BootstrapTestBase(unittest.TestCase):
    """Base con proyecto y workspace temporales externos al framework."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

        # Proyecto simulado (fuera del framework)
        self.project = self.base / "my-project"
        self.project.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src" / "main.py").write_text("print('hello')\n")
        (self.project / "README.md").write_text("# My Project\n")
        (self.project / "AGENTS.md").write_text("# Instructions\nrules here\n")

        # Workspace (hermano del proyecto, fuera de Git)
        self.workspace = self.base / "my-project-workspace"

        # Never let integration tests fall through to the user's real DSH home.
        self.dsh_home = self.base / "dsh-home"
        self.dsh_home.mkdir()
        self._env = unittest.mock.patch.dict(
            os.environ, {"DSH_HOME": str(self.dsh_home)})
        self._env.start()
        self.addCleanup(self._env.stop)


# ===========================================================================
# Positive corpus: install crea un run completo
# ===========================================================================


class TestInstallPositive(_BootstrapTestBase):
    """Install crea run con estructura completa."""

    def test_install_creates_run_directory(self):
        result = bs.install(self.project, self.workspace)
        self.assertEqual(result["result"], "CREATED")
        self.assertIn("generation_id", result)
        run_dir = Path(result["run_dir"])
        self.assertTrue(run_dir.is_dir())

    def test_install_creates_run_json(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        run_json = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run_json["schema_version"], 1)
        self.assertEqual(run_json["status"], "CREATED")
        self.assertEqual(run_json["generation_id"], result["generation_id"])
        self.assertEqual(run_json["project"]["name"], "my-project")

    def test_install_creates_all_subdirectories(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        for subdir in ("inputs", "discovery", "design", "tests",
                       "generated", "validation", "acceptance",
                       "retained", "backup", "promotion"):
            self.assertTrue((run_dir / subdir).is_dir(),
                            f"Missing subdirectory: {subdir}")

    def test_install_creates_inputs(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        for name in ("bootstrap-request.json", "snapshot.json",
                     "inventory.json", "authority.json",
                     "host-policy.json", "effective-routing.json",
                     "runtime-capabilities.json"):
            self.assertTrue((run_dir / "inputs" / name).is_file(),
                            f"Missing input: {name}")

    def test_install_snapshots_library_with_digest(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        library = json.loads((run_dir / "inputs" / "library.json").read_text())
        self.assertGreaterEqual(len(library["base_skills"]), 21)
        request = json.loads(
            (run_dir / "inputs" / "bootstrap-request.json").read_text())
        self.assertEqual(len(request["library_sha256"]), 64)

    def test_install_creates_discovery(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        for name in ("instructions-index.json", "project-manifest.json"):
            self.assertTrue((run_dir / "discovery" / name).is_file(),
                            f"Missing discovery: {name}")

    def test_install_creates_checkpoint(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        cp = json.loads((run_dir / "checkpoint.json").read_text())
        self.assertEqual(cp["phase"], "CREATED")
        self.assertTrue(cp["resumable"])
        self.assertIn("preflight", cp["completed_phases"])
        self.assertIn("creator_call", cp["pending_phases"])

    def test_install_detects_languages(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        inv = json.loads((run_dir / "inputs" / "inventory.json").read_text())
        self.assertIn("python", inv["languages"])

    def test_install_detects_instructions(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        idx = json.loads(
            (run_dir / "discovery" / "instructions-index.json").read_text()
        )
        paths = [e["path"] for e in idx["entries"]]
        self.assertIn("AGENTS.md", paths)

    def test_install_creates_workspace_identity(self):
        bs.install(self.project, self.workspace)
        self.assertTrue((self.workspace / "project.json").is_file())
        identity = json.loads((self.workspace / "project.json").read_text())
        self.assertEqual(identity["name"], "my-project")

    def test_install_host_policy_constraints(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        policy = json.loads(
            (run_dir / "inputs" / "host-policy.json").read_text()
        )
        self.assertTrue(policy["fail_closed"])
        self.assertTrue(policy["no_credentials_in_artifacts"])
        self.assertTrue(policy["creator_cannot_accept"])

    def test_install_inventory_counts_files(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        inv = json.loads((run_dir / "inputs" / "inventory.json").read_text())
        self.assertGreaterEqual(inv["total_files"], 2)
        self.assertGreater(inv["total_bytes"], 0)

    def test_install_detects_areas(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        inv = json.loads((run_dir / "inputs" / "inventory.json").read_text())
        area_names = [a["name"] for a in inv["areas"]]
        self.assertIn("src", area_names)


# ===========================================================================
# Idempotency: repetición es no-op
# ===========================================================================


class TestInstallIdempotency(_BootstrapTestBase):
    """Repetición de install devuelve la generación existente."""

    def test_second_install_returns_existing(self):
        r1 = bs.install(self.project, self.workspace)
        self.assertEqual(r1["result"], "CREATED")
        r2 = bs.install(self.project, self.workspace)
        self.assertEqual(r2["result"], "EXISTING")
        self.assertEqual(r2["generation_id"], r1["generation_id"])

    def test_existing_workspace_with_same_identity(self):
        bs.install(self.project, self.workspace)
        # Second install on same workspace is idempotent
        r2 = bs.install(self.project, self.workspace)
        self.assertIn(r2["result"], ("EXISTING", "CREATED"))

    def test_workspace_directory_not_recreated(self):
        bs.install(self.project, self.workspace)
        mtime_before = self.workspace.stat().st_mtime
        bs.install(self.project, self.workspace)
        mtime_after = self.workspace.stat().st_mtime
        self.assertEqual(mtime_before, mtime_after)


# ===========================================================================
# Product and global config unchanged
# ===========================================================================


class TestProductUnchanged(_BootstrapTestBase):
    """Install no modifica producto ni configuración global."""

    def test_project_files_unchanged(self):
        before = {}
        for f in self.project.rglob("*"):
            if f.is_file():
                before[str(f.relative_to(self.project))] = f.read_bytes()

        bs.install(self.project, self.workspace)

        after = {}
        for f in self.project.rglob("*"):
            if f.is_file():
                after[str(f.relative_to(self.project))] = f.read_bytes()

        self.assertEqual(before, after)

    def test_no_files_created_in_project(self):
        files_before = set(
            str(f.relative_to(self.project))
            for f in self.project.rglob("*") if f.is_file()
        )
        bs.install(self.project, self.workspace)
        files_after = set(
            str(f.relative_to(self.project))
            for f in self.project.rglob("*") if f.is_file()
        )
        self.assertEqual(files_before, files_after)


# ===========================================================================
# Accept subcommand
# ===========================================================================


class TestAccept(_BootstrapTestBase):
    """Accept valida un paquete generado y transiciona a VALIDATING."""

    def _make_generated(self, run_dir, gen_id="test-gen"):
        """Create a minimal valid generated/ directory.

        The manifest lists only generated content files, not itself,
        to avoid the self-referential hash problem.
        """
        gen_dir = Path(run_dir) / "generated"
        skill_dir = gen_dir / "skills" / "my-project-auditor"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# My Project Auditor\n")

        manifest = {
            "schema_version": 1,
            "generation_id": gen_id,
            "status": "GENERATED",
            "project": {
                "name": "my-project",
                "root_identity": "a" * 64,
                "base_revision": "rev-001",
            },
            "creator": {
                "session_ref": "sess-001",
                "runtime_version": "1.0.0",
            },
            "framework": {"revision": "abc123"},
            "artifacts": [
                {
                    "path": "skills/my-project-auditor/SKILL.md",
                    "type": "skill-entrypoint",
                    "sha256": bs._digest_file(skill_file),
                },
            ],
            "required_capabilities": [],
            "forbidden_capabilities": [],
            "effective_routing_digest": "b" * 64,
            "context_policy": {
                "skill_entrypoint_max_bytes": 32768,
                "support_file_max_bytes": 24576,
                "warning_ratio": 0.9,
            },
            "license_provenance": [],
        }
        manifest_path = gen_dir / "generation-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        return gen_dir

    def test_accept_transitions_to_validating(self):
        r = bs.install(self.project, self.workspace)
        run_dir = Path(r["run_dir"])
        gen_id = r["generation_id"]
        gen_dir = self._make_generated(run_dir, gen_id=gen_id)

        result = bs.accept(self.workspace, gen_dir)
        self.assertEqual(result["result"], "ACCEPT_REQUESTED")

        updated_run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(updated_run["status"], "VALIDATING")

    def test_accept_rejects_missing_manifest(self):
        r = bs.install(self.project, self.workspace)
        run_dir = Path(r["run_dir"])
        gen_dir = run_dir / "generated"
        with self.assertRaises(ValueError) as ctx:
            bs.accept(self.workspace, gen_dir)
        self.assertIn("generation-manifest.json", str(ctx.exception))

    def test_accept_creates_request_json(self):
        r = bs.install(self.project, self.workspace)
        run_dir = Path(r["run_dir"])
        gen_id = r["generation_id"]
        gen_dir = self._make_generated(run_dir, gen_id=gen_id)

        bs.accept(self.workspace, gen_dir)
        req = json.loads(
            (run_dir / "acceptance" / "request.json").read_text()
        )
        self.assertEqual(req["generation_id"], gen_id)
        self.assertEqual(req["source"], "creator")

    def test_verify_acceptance_reports_status(self):
        r = bs.install(self.project, self.workspace)
        run_dir = Path(r["run_dir"])
        gen_id = r["generation_id"]
        gen_dir = self._make_generated(run_dir, gen_id=gen_id)
        bs.accept(self.workspace, gen_dir)

        report = bs.verify_acceptance(self.workspace, generation_id=gen_id)
        self.assertEqual(report["generation_id"], gen_id)
        self.assertEqual(report["run_status"], "VALIDATING")
        self.assertTrue(report["acceptance_request_present"])


# ===========================================================================
# Update subcommand
# ===========================================================================


class TestInstallDispatch(_BootstrapTestBase):
    """install puede encadenar el despacho a Creator (fail-closed)."""

    def test_dispatch_embeds_creator_result(self):
        import creator_client as cc
        with unittest.mock.patch.object(
                cc, "run_creator",
                return_value={"result": "PREPARED",
                              "message": "sin sesión DSH autenticada"}):
            result = bs.install(self.project, self.workspace,
                                dispatch_creator=True)
        self.assertEqual(result["result"], "CREATED")
        self.assertEqual(result["creator"]["result"], "PREPARED")
        self.assertIn("Creator", result["message"])

    def test_dispatch_failure_keeps_run_recoverable(self):
        import creator_client as cc
        with unittest.mock.patch.object(
                cc, "run_creator",
                side_effect=RuntimeError("DSH inalcanzable")):
            result = bs.install(self.project, self.workspace,
                                dispatch_creator=True)
        self.assertEqual(result["result"], "CREATED")
        self.assertEqual(result["creator"]["result"], "PREPARED")
        self.assertIn("DSH inalcanzable", result["creator"]["error"])

    def test_default_does_not_dispatch(self):
        import creator_client as cc
        with unittest.mock.patch.object(
                cc, "run_creator",
                side_effect=AssertionError("must not dispatch")):
            result = bs.install(self.project, self.workspace)
        self.assertEqual(result["result"], "CREATED")
        self.assertNotIn("creator", result)

    def test_existing_generating_run_is_resumed(self):
        """--launch-dsh on an in-progress run dispatches instead of EXISTING."""
        import creator_client as cc
        first = bs.install(self.project, self.workspace)
        run_dir = Path(first["run_dir"])
        run_doc = json.loads((run_dir / "run.json").read_text())
        run_doc["status"] = "GENERATING"
        (run_dir / "run.json").unlink()
        bs._write_json(run_dir / "run.json", run_doc)

        with unittest.mock.patch.object(
                cc, "run_creator",
                return_value={"result": "PREPARED",
                              "message": "sin sesión DSH autenticada"}) as mocked:
            result = bs.install(self.project, self.workspace,
                                dispatch_creator=True)
        mocked.assert_called_once()
        self.assertEqual(result["result"], "EXISTING")
        self.assertEqual(result["status"], "GENERATING")
        self.assertEqual(result["creator"]["result"], "PREPARED")

    def test_existing_generated_run_is_not_dispatched(self):
        """Host-owned states are never re-dispatched."""
        import creator_client as cc
        first = bs.install(self.project, self.workspace)
        run_dir = Path(first["run_dir"])
        run_doc = json.loads((run_dir / "run.json").read_text())
        run_doc["status"] = "VALIDATING"
        (run_dir / "run.json").unlink()
        bs._write_json(run_dir / "run.json", run_doc)

        with unittest.mock.patch.object(
                cc, "run_creator",
                side_effect=AssertionError("must not dispatch")):
            result = bs.install(self.project, self.workspace,
                                dispatch_creator=True)
        self.assertEqual(result["result"], "EXISTING")
        self.assertNotIn("creator", result)


class TestUpdate(_BootstrapTestBase):
    """Update detecta base cambiada o devuelve no-op."""

    def test_update_without_active_raises(self):
        self.workspace.mkdir()
        with self.assertRaises(ValueError) as ctx:
            bs.update(self.project, self.workspace)
        self.assertIn("activa", str(ctx.exception))

    def test_update_with_in_progress_returns_in_progress(self):
        r1 = bs.install(self.project, self.workspace)
        # Run is CREATED (in progress)
        result = bs.update(self.project, self.workspace)
        self.assertEqual(result["result"], "IN_PROGRESS")

    def test_install_identity_matches_shared_derivation(self):
        r1 = bs.install(self.project, self.workspace)
        run_dir = Path(r1["run_dir"])
        run_doc = json.loads((run_dir / "run.json").read_text())
        expected = bs._root_identity(self.project, bs._git_info(self.project))
        self.assertEqual(run_doc["project"]["root_identity"], expected)

    def test_update_same_base_returns_no_op(self):
        """Identity comparison must match install derivation even without git."""
        r1 = bs.install(self.project, self.workspace)
        run_dir = Path(r1["run_dir"])
        run_doc = json.loads((run_dir / "run.json").read_text())
        run_doc["status"] = "ACTIVE"
        (run_dir / "run.json").unlink()
        bs._write_json(run_dir / "run.json", run_doc)

        result = bs.update(self.project, self.workspace)
        self.assertEqual(result["result"], "NO_OP")


# ===========================================================================
# Uninstall subcommand
# ===========================================================================


class TestUninstall(_BootstrapTestBase):
    """Uninstall retira solo gestionados; preserva producto."""

    def test_uninstall_without_workspace_raises(self):
        with self.assertRaises(ValueError):
            bs.uninstall(self.project, self.base / "nonexistent")

    def test_uninstall_marks_active_as_rolled_back(self):
        r = bs.install(self.project, self.workspace)
        run_dir = Path(r["run_dir"])
        # Manually set to ACTIVE
        run_doc = json.loads((run_dir / "run.json").read_text())
        run_doc["status"] = "ACTIVE"
        (run_dir / "run.json").unlink()
        bs._write_json(run_dir / "run.json", run_doc)

        result = bs.uninstall(self.project, self.workspace)
        self.assertEqual(result["result"], "UNINSTALLED")

        updated = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(updated["status"], "ROLLED_BACK")

    def test_uninstall_preserves_project(self):
        before = (self.project / "src" / "main.py").read_bytes()
        bs.install(self.project, self.workspace)
        bs.uninstall(self.project, self.workspace)
        after = (self.project / "src" / "main.py").read_bytes()
        self.assertEqual(before, after)

    def test_uninstall_result_lists_preserved(self):
        bs.install(self.project, self.workspace)
        result = bs.uninstall(self.project, self.workspace)
        self.assertIn("product", result["preserved"])
        self.assertIn("backups", result["preserved"])

    def test_legacy_uninstall_without_receipt_does_not_acquire_or_touch_dsh(self):
        sentinel = self.dsh_home / ".agent-presets" / "foreign" / "keep"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("untouched\n")
        bs.install(self.project, self.workspace)
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                side_effect=AssertionError("legacy uninstall must not acquire DSH")):
            result = bs.uninstall(self.project, self.workspace)
        self.assertEqual(result["result"], "UNINSTALLED")
        self.assertEqual(sentinel.read_text(), "untouched\n")

    def test_uninstall_with_receipt_uses_acquired_authoritative_home(self):
        bs.install(self.project, self.workspace)
        managed = self.workspace / ".dsh-managed"
        managed.mkdir()
        (managed / "published-presets.json").write_text("{}\n")
        authoritative = self.base / "authoritative-dsh-home"
        client = unittest.mock.Mock(resolved_dsh_home=authoritative)
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(client, "runtime")), \
             unittest.mock.patch("transaction.uninstall", return_value={
                 "result": "UNINSTALLED", "removed_presets": [],
             }) as uninstall:
            bs.uninstall(self.project, self.workspace)
        uninstall.assert_called_once_with(
            self.workspace, dsh_home=authoritative)


# ===========================================================================
# Purge-data subcommand
# ===========================================================================


class TestPurgeData(_BootstrapTestBase):
    """Purge-data elimina runs con confirmación."""

    def test_purge_dry_run(self):
        bs.install(self.project, self.workspace)
        result = bs.purge_data(self.workspace, confirm=False)
        self.assertEqual(result["result"], "DRY_RUN")
        self.assertGreater(len(result["runs_to_delete"]), 0)
        # Data still exists
        self.assertTrue(
            (self.workspace / bs.RUN_DIR_NAME).is_dir()
        )

    def test_purge_with_confirm_deletes(self):
        bs.install(self.project, self.workspace)
        result = bs.purge_data(self.workspace, confirm=True)
        self.assertEqual(result["result"], "PURGED")
        self.assertFalse(
            (self.workspace / bs.RUN_DIR_NAME).is_dir()
        )

    def test_purge_no_data(self):
        self.workspace.mkdir()
        result = bs.purge_data(self.workspace)
        self.assertEqual(result["result"], "NO_DATA")

    def test_purge_rejects_symlinks(self):
        bs.install(self.project, self.workspace)
        runs = self.workspace / bs.RUN_DIR_NAME
        # Create a symlink inside runs
        for run_dir in runs.iterdir():
            if run_dir.is_dir():
                link = run_dir / "sneaky-link"
                link.symlink_to(self.project)
                break
        with self.assertRaises(ValueError) as ctx:
            bs.purge_data(self.workspace, confirm=True)
        self.assertIn("simbólico", str(ctx.exception))


# ===========================================================================
# Negative corpus: errores dejan estado limpio
# ===========================================================================


class TestNegativeCorpus(_BootstrapTestBase):
    """Cada caso negativo falla cerrado sin dejar estado parcial."""

    def test_missing_project(self):
        with self.assertRaises(ValueError):
            bs.install(self.base / "nonexistent", self.workspace)

    def test_workspace_inside_project(self):
        ws = self.project / "workspace"
        with self.assertRaises(ValueError):
            bs.install(self.project, ws)

    def test_project_inside_workspace(self):
        self.workspace.mkdir()
        proj = self.workspace / "proj"
        proj.mkdir()
        (proj / "file.py").write_text("x = 1\n")
        with self.assertRaises(ValueError):
            bs.install(proj, self.workspace)

    def test_workspace_is_framework(self):
        with self.assertRaises(ValueError):
            bs.install(self.project, bs.FRAMEWORK)

    def test_project_is_framework(self):
        with self.assertRaises(ValueError):
            bs.install(bs.FRAMEWORK, self.workspace)

    def test_symlink_project(self):
        link = self.base / "linked-project"
        link.symlink_to(self.project)
        with self.assertRaises(ValueError):
            bs.install(link, self.workspace)

    def test_symlink_workspace_path(self):
        real = self.base / "real-ws"
        real.mkdir()
        link = self.base / "link-ws"
        link.symlink_to(real)
        with self.assertRaises(ValueError):
            bs.install(self.project, link)

    def test_workspace_parent_missing(self):
        ws = self.base / "missing" / "deep" / "workspace"
        with self.assertRaises(ValueError):
            bs.install(self.project, ws)

    def test_workspace_conflict_different_identity(self):
        self.workspace.mkdir()
        bs._write_json(self.workspace / "project.json", {
            "schema": 1,
            "name": "other-project",
            "project": str(self.project),
        })
        with self.assertRaises(ValueError) as ctx:
            bs.install(self.project, self.workspace)
        self.assertIn("identidad diferente", str(ctx.exception))

    def test_workspace_is_file(self):
        self.workspace.parent.mkdir(parents=True, exist_ok=True)
        self.workspace.write_text("not a dir")
        with self.assertRaises(ValueError):
            bs.install(self.project, self.workspace)

    def test_accept_nonexistent_workspace(self):
        with self.assertRaises(ValueError):
            bs.accept(self.base / "nope", self.base / "gen")

    def test_accept_nonexistent_generated(self):
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            bs.accept(self.workspace, self.base / "gen")

    def test_uninstall_nonexistent_workspace(self):
        with self.assertRaises(ValueError):
            bs.uninstall(self.project, self.base / "nope")

    def test_purge_nonexistent_workspace(self):
        with self.assertRaises(ValueError):
            bs.purge_data(self.base / "nope")


# ===========================================================================
# No credentials or secrets in outputs
# ===========================================================================


class TestNoSecrets(_BootstrapTestBase):
    """Ningún archivo generado contiene credenciales o rutas del mantenedor."""

    def test_no_secrets_in_run_files(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        forbidden = ["api_key", "password", "secret", "token",
                      "bearer", "authorization"]
        for json_file in run_dir.rglob("*.json"):
            if json_file.is_file() and not json_file.is_symlink():
                content = json_file.read_text().lower()
                for word in forbidden:
                    if word in content:
                        # Check it's not a field name we legitimately use
                        parsed = json.loads(json_file.read_text())
                        text = json.dumps(parsed, indent=2).lower()
                        self.assertNotIn(
                            f'"{word}":', text,
                            f"Possible secret in {json_file.name}: {word}",
                        )

    def test_routing_has_digest_not_credentials(self):
        result = bs.install(self.project, self.workspace)
        run_dir = Path(result["run_dir"])
        routing = json.loads(
            (run_dir / "inputs" / "effective-routing.json").read_text()
        )
        self.assertIn("routing_digest", routing)
        # Should not contain raw DSH info
        text = json.dumps(routing)
        self.assertNotIn("api_key", text)
        self.assertNotIn("password", text)


# ===========================================================================
# Preflight
# ===========================================================================


class TestPreflight(_BootstrapTestBase):
    """Preflight valida correctamente y rechaza configuraciones inválidas."""

    def test_preflight_returns_info(self):
        result = bs.preflight(self.project, self.workspace)
        self.assertIn("project", result)
        self.assertIn("workspace", result)
        self.assertIn("framework", result)
        self.assertIn("dsh", result)
        self.assertIn("timestamp", result)

    def test_preflight_overlap_rejected(self):
        with self.assertRaises(ValueError):
            bs.preflight(self.project, self.project / "sub")


if __name__ == "__main__":
    unittest.main()
