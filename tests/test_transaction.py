"""Tests C4 de backup, staging, swap atómico y rollback."""

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acceptance
import transaction as tx


def _verdict(generation_id="gen-1", verdict="ACTIVE"):
    """Host verdict as acceptance would emit it (acceptance/host-verdict.json)."""
    return {
        "schema_version": 1,
        "generation_id": generation_id,
        "verdict": verdict,
        "timestamp": "2026-09-19T00:00:00+00:00",
        "source": "host-acceptance",
    }


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

    def _install(self, generated=None, generation_id="gen-1",
                 verdict="ACTIVE", **kwargs):
        kwargs.setdefault("host_verdict", _verdict(generation_id, verdict))
        return tx.install(self.workspace, generated or self.generated,
                          generation_id, **kwargs)

    def test_install_requires_host_verdict(self):
        with self.assertRaises(tx.TransactionError) as ctx:
            tx.install(self.workspace, self.generated, "gen-1")
        self.assertIn("Veredicto Host", str(ctx.exception))

    def test_install_rejects_non_active_verdict(self):
        with self.assertRaises(tx.TransactionError) as ctx:
            self._install(verdict="RETAINED")
        self.assertIn("no aprobó", str(ctx.exception))
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_install_rejects_early_retained_file_before_staging(self):
        retained_path = self.root / "static-retained.json"
        retained_path.write_text(json.dumps({
            "schema_version": 1,
            "generation_id": "gen-1",
            "verdict": "RETAINED",
            "stage": "STATIC_VALIDATION",
            "reason": "static failed",
        }))
        with self.assertRaisesRegex(tx.TransactionError, "no aprobó"):
            tx.install(self.workspace, self.generated, "gen-1",
                       host_verdict=retained_path)
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_install_rejects_verdict_for_other_generation(self):
        with self.assertRaises(tx.TransactionError) as ctx:
            self._install(generation_id="gen-1",
                          host_verdict=_verdict(generation_id="gen-9"))
        self.assertIn("otra generación", str(ctx.exception))

    def test_install_accepts_verdict_file(self):
        acceptance_dir = self.root / "acceptance"
        acceptance_dir.mkdir()
        public = acceptance_dir / "public-results.json"
        holdout = acceptance_dir / "holdout-results.json"
        review = acceptance_dir / "independent-review.json"
        for path in (public, holdout, review):
            path.write_text("{}\n", encoding="utf-8")
        verdict_path = acceptance_dir / "host-verdict.json"
        verdict = {
            "schema_version": 1, "generation_id": "gen-1",
            "verdict": "ACTIVE", "static_passed": True,
            "public_passed": True, "holdout_passed": True,
            "independent_review": "PASS",
            "candidate_digest": acceptance.tree_digest(self.generated),
            "manifest_digest": acceptance._digest_file(
                self.generated / "generation-manifest.json"),
            "public_results_digest": acceptance._digest_file(public),
            "holdout_results_digest": acceptance._digest_file(holdout),
            "review_digest": acceptance._digest_file(review),
            "host_policy_digest": acceptance.current_host_policy_digest(),
            "timestamp": "2026-09-19T00:00:00+00:00",
        }
        verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
        result = tx.install(self.workspace, self.generated, "gen-1",
                            host_verdict=verdict_path)
        self.assertEqual(result["result"], "ACTIVE")

    def test_install_rejects_verdict_from_stale_host_policy(self):
        acceptance_dir = self.root / "acceptance"
        acceptance_dir.mkdir()
        public = acceptance_dir / "public-results.json"
        holdout = acceptance_dir / "holdout-results.json"
        review = acceptance_dir / "independent-review.json"
        for path in (public, holdout, review):
            path.write_text("{}\n", encoding="utf-8")
        verdict_path = acceptance_dir / "host-verdict.json"
        verdict = {
            "schema_version": 1, "generation_id": "gen-1",
            "verdict": "ACTIVE", "static_passed": True,
            "public_passed": True, "holdout_passed": True,
            "independent_review": "PASS",
            "candidate_digest": acceptance.tree_digest(self.generated),
            "manifest_digest": acceptance._digest_file(
                self.generated / "generation-manifest.json"),
            "public_results_digest": acceptance._digest_file(public),
            "holdout_results_digest": acceptance._digest_file(holdout),
            "review_digest": acceptance._digest_file(review),
            "host_policy_digest": acceptance.current_host_policy_digest(),
            "timestamp": "2026-09-19T00:00:00+00:00",
        }
        verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

        with unittest.mock.patch.object(
                acceptance, "HOST_POLICY_VERSION",
                acceptance.HOST_POLICY_VERSION + "-changed"):
            with self.assertRaisesRegex(ValueError, "cambió la política Host"):
                tx.install(self.workspace, self.generated, "gen-1",
                           host_verdict=verdict_path)
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_install_rejects_unbound_minimal_verdict_file(self):
        verdict_path = self.root / "host-verdict.json"
        verdict_path.write_text(json.dumps(_verdict("gen-1")), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "campos inválidos"):
            tx.install(self.workspace, self.generated, "gen-1",
                       host_verdict=verdict_path)

    def test_install_activates_generation(self):
        result = self._install()
        self.assertEqual(result["result"], "ACTIVE")
        managed = self.workspace / ".dsh-managed"
        self.assertEqual((managed / "ACTIVE").read_text().strip(), "gen-1")
        self.assertTrue((managed / "generations" / "gen-1").is_dir())
        self.assertTrue((managed / "backups" / "gen-1.json").is_file())

    def test_install_is_idempotent(self):
        first = self._install()
        second = self._install()
        self.assertEqual(second["result"], "NO_OP")

    def test_install_creates_verified_backup(self):
        self._install()
        newer = self.root / "newer"
        newer.mkdir()
        (newer / "generation-manifest.json").write_text("new\n")
        result = self._install(generated=newer, generation_id="gen-2")
        self.assertEqual(result["previous_generation_id"], "gen-1")
        backup = json.loads((self.workspace / ".dsh-managed" / "backups" / "gen-2.json").read_text())
        self.assertTrue(backup["verified"])
        self.assertEqual(backup["previous_generation_id"], "gen-1")

    def test_rollback_restores_previous(self):
        self._install()
        newer = self.root / "newer"
        newer.mkdir()
        (newer / "generation-manifest.json").write_text("new\n")
        self._install(generated=newer, generation_id="gen-2")
        result = tx.rollback(self.workspace, "gen-2")
        self.assertEqual(result["result"], "ROLLED_BACK")
        self.assertEqual(result["rolled_back_to"], "gen-1")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(), "gen-1")

    def test_uninstall_removes_pointer_preserves_backups(self):
        self._install()
        result = tx.uninstall(self.workspace)
        self.assertEqual(result["result"], "UNINSTALLED")
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())
        self.assertTrue((self.workspace / ".dsh-managed" / "backups" / "gen-1.json").exists())

    def test_symlink_rejected(self):
        target = self.root / "target"
        target.write_text("x")
        (self.generated / "link").symlink_to(target)
        with self.assertRaises(ValueError):
            self._install()

    def test_missing_manifest_rejected(self):
        (self.generated / "generation-manifest.json").unlink()
        with self.assertRaises(tx.TransactionError):
            self._install()

    def test_rollback_missing_backup_rejected(self):
        with self.assertRaises(tx.TransactionError):
            tx.rollback(self.workspace, "none")


if __name__ == "__main__":
    unittest.main()
