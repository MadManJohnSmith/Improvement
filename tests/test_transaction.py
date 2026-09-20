"""Transactional publication of exactly two DSH user presets."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import transaction as tx


class Client:
    def __init__(self, ids=("project-auditor", "project-continuous-repair"), broken=None):
        self.ids = ids
        self.broken = broken
        self.authenticated = True
    def list_agent_presets(self):
        return {"value": {"items": [
            {"id": value, "trust": "user", "broken": value == self.broken}
            for value in self.ids]}}


def verdict(generation="gen-1", value="READY_FOR_INSTALL"):
    return {"generation_id": generation, "verdict": value}


class TransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "project-workspace"
        self.workspace.mkdir()
        (self.workspace / "project.json").write_text(json.dumps({
            "schema": 1, "name": "project", "project": str(self.root / "project")}) + "\n")
        (self.root / "project").mkdir()
        self.home = self.root / "dsh-home"
        self.generated = self._package(self.root / "generated")

    def _package(self, root, marker="one"):
        root.mkdir()
        (root / "generation-manifest.json").write_text("{}\n")
        for role in ("auditor", "continuous-repair"):
            preset_id = f"project-{role}"
            mode = root / "modes" / preset_id
            mode.mkdir(parents=True)
            (mode / "mode.json").write_text(json.dumps({
                "preset_id": preset_id, "role": role}) + "\n")
            (mode / "preset.yml").write_text(f"name: {preset_id}\n")
            (mode / "agent.cordis.yml").write_text(f"# {marker}\n")
            (mode / "SKILL.md").write_text(f"# {preset_id}\n")
        return root

    def install(self, generated=None, generation="gen-1", client=None, **kwargs):
        return tx.install(self.workspace, generated or self.generated, generation,
                          host_verdict=kwargs.pop("host_verdict", verdict(generation)),
                          dsh_home=self.home, client=client or Client(), **kwargs)

    def test_requires_host_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "Veredicto Host"):
            tx.install(self.workspace, self.generated, "gen-1",
                       dsh_home=self.home, client=Client())

    def test_rejects_non_installable_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "no aprobó"):
            self.install(host_verdict=verdict(value="RETAINED"))

    def test_publishes_two_presets_and_shared_state_then_activates(self):
        result = self.install()
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), {
            "project-auditor", "project-continuous-repair"})
        for preset_id in result["published_presets"]:
            self.assertTrue((self.home / ".agent-presets" / preset_id).is_dir())
        descriptor = json.loads((self.workspace / "mode-state" / "project.json").read_text())
        self.assertEqual(descriptor["product_root"], "project")
        self.assertEqual(descriptor["state_root"], "project-workspace/mode-state")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(), "gen-1")

    def test_roster_failure_rolls_back_both_presets_and_no_active_pointer(self):
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(client=Client(ids=("project-auditor",)))
        root = self.home / ".agent-presets"
        self.assertFalse((root / "project-auditor").exists())
        self.assertFalse((root / "project-continuous-repair").exists())
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())

    def test_broken_roster_entry_rolls_back(self):
        with self.assertRaisesRegex(tx.TransactionError, "sano"):
            self.install(client=Client(broken="project-continuous-repair"))

    def test_foreign_preset_is_preserved_and_blocks_install(self):
        foreign = self.home / ".agent-presets" / "project-auditor"
        foreign.mkdir(parents=True)
        (foreign / "foreign").write_text("keep")
        with self.assertRaisesRegex(tx.TransactionError, "ajeno"):
            self.install()
        self.assertEqual((foreign / "foreign").read_text(), "keep")

    def test_uninstall_removes_unmodified_managed_presets_preserves_state(self):
        self.install()
        result = tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(set(result["removed_presets"]), {
            "project-auditor", "project-continuous-repair"})
        self.assertTrue((self.workspace / "mode-state" / "project.json").is_file())
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())

    def test_uninstall_refuses_modified_managed_preset(self):
        self.install()
        preset = self.home / ".agent-presets" / "project-auditor" / "SKILL.md"
        preset.write_text("modified\n")
        with self.assertRaisesRegex(tx.TransactionError, "modificado"):
            tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertTrue(preset.is_file())

    def test_uninstall_prevalidates_second_preset_before_deleting_first(self):
        self.install()
        root = self.home / ".agent-presets"
        second = root / "project-continuous-repair" / "SKILL.md"
        second.write_text("modified\n")
        with self.assertRaisesRegex(tx.TransactionError, "modificado"):
            tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertTrue((root / "project-auditor").is_dir())
        self.assertTrue((root / "project-continuous-repair").is_dir())
        self.assertTrue((self.workspace / ".dsh-managed" /
                         "published-presets.json").is_file())

    def _uninstall_state(self):
        root = self.home / ".agent-presets"
        managed = self.workspace / ".dsh-managed"
        return {
            "presets": {name: tx._inventory(root / name) for name in
                        ("project-auditor", "project-continuous-repair")},
            "receipt": (managed / "published-presets.json").read_bytes(),
            "active": (managed / "ACTIVE").read_bytes(),
            "tombstones": sorted(str(path) for path in self.root.rglob("*.tombstone")),
        }

    def test_uninstall_failure_after_first_preset_move_restores_exact_state(self):
        self.install()
        before = self._uninstall_state()
        original_rename = Path.rename
        calls = {"count": 0}

        def fail_second_move(path, target):
            if ".uninstall-" in Path(target).name:
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("injected second preset move failure")
            return original_rename(path, target)

        with unittest.mock.patch.object(Path, "rename", autospec=True,
                                        side_effect=fail_second_move):
            with self.assertRaisesRegex(tx.TransactionError, "estado original restaurado"):
                tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(self._uninstall_state(), before)

    def test_uninstall_failure_moving_receipt_restores_presets_and_active(self):
        self.install()
        before = self._uninstall_state()
        original_rename = Path.rename

        def fail_receipt(path, target):
            if Path(path).name == "published-presets.json":
                raise OSError("injected receipt transition failure")
            return original_rename(path, target)

        with unittest.mock.patch.object(Path, "rename", autospec=True,
                                        side_effect=fail_receipt):
            with self.assertRaisesRegex(tx.TransactionError, "estado original restaurado"):
                tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(self._uninstall_state(), before)

    def test_uninstall_failure_moving_active_restores_receipt_and_presets(self):
        self.install()
        before = self._uninstall_state()
        original_rename = Path.rename

        def fail_active(path, target):
            if Path(path).name == "ACTIVE":
                raise OSError("injected ACTIVE transition failure")
            return original_rename(path, target)

        with unittest.mock.patch.object(Path, "rename", autospec=True,
                                        side_effect=fail_active):
            with self.assertRaisesRegex(tx.TransactionError, "estado original restaurado"):
                tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(self._uninstall_state(), before)

    def test_uninstall_cleanup_failure_reports_recovery_required_after_commit(self):
        self.install()
        original_rmtree = tx.shutil.rmtree

        def fail_tombstone_cleanup(path, *args, **kwargs):
            if ".uninstall-" in Path(path).name:
                raise OSError("injected cleanup failure")
            return original_rmtree(path, *args, **kwargs)

        with unittest.mock.patch("transaction.shutil.rmtree",
                                 side_effect=fail_tombstone_cleanup):
            result = tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(result["result"], "RECOVERY_REQUIRED")
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())
        self.assertFalse((self.workspace / ".dsh-managed" /
                          "published-presets.json").exists())
        self.assertTrue(any(self.root.rglob("*.tombstone")))

    def test_cleanup_failure_retry_uses_marker_and_finishes_uninstall(self):
        self.install()
        original_rmtree = tx.shutil.rmtree

        def fail_tombstone_cleanup(path, *args, **kwargs):
            if ".uninstall-" in Path(path).name:
                raise OSError("injected cleanup failure")
            return original_rmtree(path, *args, **kwargs)

        with unittest.mock.patch("transaction.shutil.rmtree",
                                 side_effect=fail_tombstone_cleanup):
            first = tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(first["result"], "RECOVERY_REQUIRED")
        marker = self.workspace / ".dsh-managed" / tx.UNINSTALL_RECOVERY_FILE
        self.assertTrue(marker.is_file())
        with self.assertRaisesRegex(tx.TransactionError, "RECOVERY_REQUIRED"):
            tx.uninstall_unpublished(self.workspace)
        second = tx.uninstall(self.workspace, dsh_home=self.home)
        self.assertEqual(second["result"], "UNINSTALLED")
        self.assertFalse(marker.exists())
        self.assertFalse(any(self.root.rglob("*.tombstone")))

    def test_rollback_after_publication_restores_presets_and_receipt(self):
        self.install()
        root = self.home / ".agent-presets"
        receipt_path = self.workspace / ".dsh-managed" / "published-presets.json"
        old_receipt = receipt_path.read_text()
        old_files = {preset_id: (root / preset_id / "agent.cordis.yml").read_text()
                     for preset_id in ("project-auditor", "project-continuous-repair")}
        generated = self._package(self.root / "generated-two", marker="two")
        original_inventory = tx._inventory
        calls = {"target": 0}

        def fail_post_publication(path):
            result = original_inventory(path)
            if Path(path) == self.workspace / ".dsh-managed" / "generations" / "gen-2":
                calls["target"] += 1
                if calls["target"] >= 1:
                    return {**result, "tampered": {"sha256": "bad", "size_bytes": 0}}
            return result

        with unittest.mock.patch("transaction._inventory", side_effect=fail_post_publication):
            with self.assertRaisesRegex(tx.TransactionError, "post-swap"):
                self.install(generated=generated, generation="gen-2")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")
        self.assertEqual(receipt_path.read_text(), old_receipt)
        for preset_id, content in old_files.items():
            self.assertEqual((root / preset_id / "agent.cordis.yml").read_text(), content)

    def test_update_rollback_then_same_generation_retry_reuses_original_backup(self):
        self.install()
        root = self.home / ".agent-presets"
        generated = self._package(self.root / "generated-two", marker="two")
        old_bytes = {preset_id: (root / preset_id / "agent.cordis.yml").read_bytes()
                     for preset_id in ("project-auditor", "project-continuous-repair")}
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(generated=generated, generation="gen-2",
                         client=Client(ids=("project-auditor",)))
        backup = self.workspace / ".dsh-managed" / "backups" / "gen-2"
        manifest = self.workspace / ".dsh-managed" / "backups" / "gen-2.json"
        backup_before = tx._inventory(backup)
        manifest_before = manifest.read_bytes()

        result = self.install(generated=generated, generation="gen-2")
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(tx._inventory(backup), backup_before)
        self.assertEqual(manifest.read_bytes(), manifest_before)
        for preset_id, content in old_bytes.items():
            self.assertEqual((backup / "agent-presets" / preset_id /
                              "agent.cordis.yml").read_bytes(), content)

    def test_retry_after_roster_failure_republishes_incomplete_generation(self):
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(client=Client(ids=("project-auditor",)))
        result = self.install(client=Client())
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")

    def test_transaction_requires_explicit_resolved_home(self):
        with self.assertRaisesRegex(tx.TransactionError, "home resuelto"):
            tx.Transaction(self.workspace, dsh_home=None)

    def test_direct_install_cli_requires_dsh_home(self):
        result = subprocess.run([
            sys.executable, "-B", str(ROOT / "scripts" / "transaction.py"),
            "install", "--workspace", str(self.workspace), "--generated",
            str(self.generated), "--generation-id", "gen-1",
            "--host-verdict", str(self.root / "verdict.json")],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--dsh-home", result.stderr)

    def _direct_install_args(self):
        verdict_path = self.root / "verdict.json"
        verdict_path.write_text(json.dumps(verdict()) + "\n")
        return [
            "install", "--workspace", str(self.workspace), "--generated",
            str(self.generated), "--generation-id", "gen-1",
            "--host-verdict", str(verdict_path), "--dsh-home", str(self.home),
        ]

    def test_direct_install_cli_succeeds_with_authenticated_matching_client(self):
        client = Client()
        client.resolved_dsh_home = self.home
        stdout = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(client, "controlled runtime")) as acquire, \
             unittest.mock.patch("acceptance.validate_host_verdict",
                                 return_value=verdict()), \
             contextlib.redirect_stdout(stdout):
            tx.main(self._direct_install_args())
        acquire.assert_called_once_with(launch=False)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), {
            "project-auditor", "project-continuous-repair"})
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")

    def test_direct_install_cli_fails_when_no_authenticated_runtime_available(self):
        stderr = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(None, "sin sesión DSH autenticada")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as failure:
                tx.main(self._direct_install_args())
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("DSH no disponible", stderr.getvalue())
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_install_cli_fails_when_runtime_home_mismatches_argument(self):
        client = Client()
        client.resolved_dsh_home = self.root / "other-dsh-home"
        stderr = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(client, "controlled runtime")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as failure:
                tx.main(self._direct_install_args())
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("no coincide con --dsh-home", stderr.getvalue())
        self.assertFalse((self.workspace / ".dsh-managed").exists())


if __name__ == "__main__":
    unittest.main()
