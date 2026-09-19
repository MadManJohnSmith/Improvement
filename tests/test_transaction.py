"""Tests C4 de backup, staging, swap atómico y rollback."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import transaction as tx


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.generated = self.root / "generated"
        self.generated.mkdir()
        (self.generated / "generation-manifest.json").write_text("{}\n")
        (self.generated / "skills").mkdir()
        (self.generated / "skills" / "SKILL.md").write_text("# skill\n")

    def test_install_activates_generation(self):
        result = tx.install(self.workspace, self.generated, "gen-1")
        self.assertEqual(result["result"], "ACTIVE")
        managed = self.workspace / ".dsh-managed"
        self.assertEqual((managed / "ACTIVE").read_text().strip(), "gen-1")
        self.assertTrue((managed / "generations" / "gen-1").is_dir())
        self.assertTrue((managed / "backups" / "gen-1.json").is_file())

    def test_install_is_idempotent(self):
        first = tx.install(self.workspace, self.generated, "gen-1")
        second = tx.install(self.workspace, self.generated, "gen-1")
        self.assertEqual(second["result"], "NO_OP")

    def test_install_creates_verified_backup(self):
        tx.install(self.workspace, self.generated, "gen-1")
        newer = self.root / "newer"
        newer.mkdir()
        (newer / "generation-manifest.json").write_text("new\n")
        result = tx.install(self.workspace, newer, "gen-2")
        self.assertEqual(result["previous_generation_id"], "gen-1")
        backup = json.loads((self.workspace / ".dsh-managed" / "backups" / "gen-2.json").read_text())
        self.assertTrue(backup["verified"])
        self.assertEqual(backup["previous_generation_id"], "gen-1")

    def test_rollback_restores_previous(self):
        tx.install(self.workspace, self.generated, "gen-1")
        newer = self.root / "newer"
        newer.mkdir()
        (newer / "generation-manifest.json").write_text("new\n")
        tx.install(self.workspace, newer, "gen-2")
        result = tx.rollback(self.workspace, "gen-2")
        self.assertEqual(result["result"], "ROLLED_BACK")
        self.assertEqual(result["rolled_back_to"], "gen-1")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(), "gen-1")

    def test_uninstall_removes_pointer_preserves_backups(self):
        tx.install(self.workspace, self.generated, "gen-1")
        result = tx.uninstall(self.workspace)
        self.assertEqual(result["result"], "UNINSTALLED")
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())
        self.assertTrue((self.workspace / ".dsh-managed" / "backups" / "gen-1.json").exists())

    def test_symlink_rejected(self):
        target = self.root / "target"
        target.write_text("x")
        (self.generated / "link").symlink_to(target)
        with self.assertRaises(ValueError):
            tx.install(self.workspace, self.generated, "gen-1")

    def test_missing_manifest_rejected(self):
        (self.generated / "generation-manifest.json").unlink()
        with self.assertRaises(tx.TransactionError):
            tx.install(self.workspace, self.generated, "gen-1")

    def test_rollback_missing_backup_rejected(self):
        with self.assertRaises(tx.TransactionError):
            tx.rollback(self.workspace, "none")


if __name__ == "__main__":
    unittest.main()
