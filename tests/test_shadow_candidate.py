"""E4: the candidate is a shadow repository, so the product can be read-only.

The property under test is the one that made the worktree untenable. With the
product's `.git` read-only, `git add` inside a worktree fails, because the
worktree's index lives in the product's `.git/worktrees/`. A shadow has its own
`.git`, so the product can be read-only and every git operation inside the
candidate still works.

The confinement itself is proved in `test_auditor_confinement.py` against the
real runtime. What these cases pin is the shadow's own guarantees: it shares
nothing with the product, re-provisioning does not discard work in flight, a
patch says it is a patch, and nothing here touches the operator's tree.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import shadow_candidate


def _git(root, *arguments, check=True):
    finished = subprocess.run(["git", "-C", str(root), *arguments],
                             capture_output=True, text=True)
    if check and finished.returncode != 0:
        raise AssertionError(f"git {arguments} failed: {finished.stderr}")
    return finished


class ShadowCandidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shadow-", dir="/tmp"))
        self.addCleanup(self._cleanup, self.tmp)
        self.product = self.tmp / "product"
        self.workspace = self.tmp / "workspace"
        self.product.mkdir()
        self.workspace.mkdir()
        (self.product / "a.txt").write_text("original\n", encoding="utf-8")
        (self.product / "pkg").mkdir()
        (self.product / "pkg" / "b.txt").write_text("second\n", encoding="utf-8")
        _git(self.product, "init", "-q", "-b", "main", ".")
        _git(self.product, "config", "user.email", "t@example.invalid")
        _git(self.product, "config", "user.name", "t")
        _git(self.product, "add", "-A", ".")
        _git(self.product, "commit", "-qm", "base")

    def _cleanup(self, tmp):
        for path in sorted(tmp.rglob("*"), reverse=True):
            try:
                path.chmod(0o700 if path.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    def _readonly_product_git(self):
        # What the sandbox does is mount the product read-only, so no file AND
        # no directory under it may be written. Marking only the files read-only
        # is a weaker simulation that git walks straight through: it creates
        # index.lock in the parent directory, not in the file it would replace.
        git = self.product / ".git"
        for path in sorted(git.rglob("*"), reverse=True):
            path.chmod(0o500 if path.is_dir() else stat.S_IRUSR)
        git.chmod(0o500)

    def _restore_product_git(self):
        git = self.product / ".git"
        for path in git.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        git.chmod(0o700)

    # -- the property that decided the design --------------------------------
    def test_a_worktree_cannot_be_used_when_the_product_git_is_read_only(self):
        # Why the shadow exists. Without this, a reader would assume the
        # worktree was fine and the read-only policy was the problem.
        worktree = self.tmp / "worktree-candidate"
        _git(self.product, "worktree", "add", "-q", str(worktree), "-b", "wt")
        self._readonly_product_git()
        try:
            (worktree / "new.txt").write_text("x\n", encoding="utf-8")
            failed = _git(worktree, "add", "new.txt", check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("index.lock", failed.stderr + failed.stdout)
        finally:
            self._restore_product_git()

    def test_a_shadow_is_fully_usable_with_the_product_git_read_only(self):
        # The whole point: confinement and a working candidate at once.
        candidate, created = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        self.assertTrue(created)
        self._readonly_product_git()
        try:
            (candidate / "a.txt").write_text("repaired\n", encoding="utf-8")
            _git(candidate, "add", "-A", ".")
            _git(candidate, "commit", "-qm", "fix")
            self.assertEqual(_git(candidate, "status", "--porcelain=v1").stdout, "")
            self.assertIn("repaired", (candidate / "a.txt").read_text(encoding="utf-8"))
        finally:
            self._restore_product_git()

    # -- the shadow's own guarantees ----------------------------------------
    def test_the_shadow_carries_the_working_tree_and_its_own_history(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        self.assertTrue((candidate / "a.txt").is_file())
        self.assertTrue((candidate / "pkg" / "b.txt").is_file())
        self.assertTrue((candidate / ".git").is_dir())
        self.assertFalse((candidate / ".git").resolve() ==
                         (self.product / ".git").resolve())
        _git(candidate, "status", "--porcelain=v1")
        self.assertEqual(_git(candidate, "status", "--porcelain=v1").stdout, "")

    def test_provisioning_never_touches_the_product(self):
        before = _git(self.product, "status", "--porcelain=v1").stdout
        head = _git(self.product, "rev-parse", "HEAD").stdout
        shadow_candidate.provision(self.product, self.workspace, "0123456789abcdef")
        self.assertEqual(_git(self.product, "status", "--porcelain=v1").stdout, before)
        self.assertEqual(_git(self.product, "rev-parse", "HEAD").stdout, head)

    def test_reprovisioning_an_existing_shadow_keeps_the_work_in_flight(self):
        candidate, first = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        self.assertTrue(first)
        (candidate / "a.txt").write_text("trabajo en curso\n", encoding="utf-8")
        _git(candidate, "add", "-A", ".")
        _git(candidate, "commit", "-qm", "en curso")
        again, second = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        self.assertFalse(second)
        self.assertEqual(again, candidate)
        self.assertIn("trabajo en curso",
                      (candidate / "a.txt").read_text(encoding="utf-8"))

    def test_a_candidate_directory_that_is_not_a_repository_is_refused(self):
        root = shadow_candidate.candidate_root(self.workspace, "0123456789abcdef")
        root.mkdir(parents=True)
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.provision(self.product, self.workspace,
                                       "0123456789abcdef")

    def test_an_invalid_digest_never_becomes_a_path(self):
        for bad in ("../escape", "zzz", "", "0" * 15, "0" * 17):
            with self.subTest(digest=bad):
                with self.assertRaises(shadow_candidate.ShadowError):
                    shadow_candidate.candidate_root(self.workspace, bad)

    def test_a_symlink_in_the_product_is_refused_rather_than_followed(self):
        (self.product / "link").symlink_to("/etc/passwd")
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.provision(self.product, self.workspace,
                                       "0123456789abcdef")

    def test_a_failed_provision_leaves_no_half_built_shadow(self):
        (self.product / "link").symlink_to("/etc/passwd")
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.provision(self.product, self.workspace,
                                       "0123456789abcdef")
        self.assertFalse(shadow_candidate.candidate_root(
            self.workspace, "0123456789abcdef").exists())
        staging = list((self.workspace / shadow_candidate.SHADOW_DIR).iterdir())
        self.assertEqual(staging, [], "el staging debe limpiarse tras un fallo")

    def test_verify_names_a_shadow_that_still_shares_the_product_git(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        report = shadow_candidate.verify(self.product, candidate)
        self.assertTrue(report["product_untouched"])
        self.assertIsNone(report["shadow_of"])

    def test_verify_refuses_a_worktree_that_shares_the_product_git(self):
        # The check that keeps the design honest. A candidate that is really a
        # worktree passes every other case here -- it is a repository, it is
        # clean, its HEAD is the base -- and still puts the repairer's index
        # inside the product it is supposed to be unable to touch.
        worktree = self.tmp / "not-a-shadow"
        _git(self.product, "worktree", "add", "-q", str(worktree), "-b", "wt")
        with self.assertRaises(shadow_candidate.ShadowError) as caught:
            shadow_candidate.verify(self.product, worktree)
        self.assertIn("git del producto", str(caught.exception))

    def test_verify_refuses_a_candidate_with_uncommitted_work(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        (candidate / "a.txt").write_text("sin registrar\n", encoding="utf-8")
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.verify(self.product, candidate)

    def test_the_integration_command_is_a_patch_and_does_not_run_here(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        command = shadow_candidate.diff_command(self.product, candidate)
        self.assertIn("--no-index", command)
        self.assertIn(str(self.product), command)
        self.assertIn(str(candidate), command)

    def test_the_patch_digest_changes_with_the_change_and_nothing_else(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        first = shadow_candidate.patch_digest(candidate)
        (candidate / "a.txt").write_text("otra cosa\n", encoding="utf-8")
        _git(candidate, "add", "-A", ".")
        _git(candidate, "commit", "-qm", "cambio")
        self.assertNotEqual(shadow_candidate.patch_digest(candidate), first)
        self.assertEqual(shadow_candidate.patch_digest(candidate),
                         shadow_candidate.patch_digest(candidate))

    def test_retiring_a_shadow_with_work_in_flight_is_refused(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        (candidate / "a.txt").write_text("sin integrar\n", encoding="utf-8")
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.retire(candidate)
        self.assertTrue(candidate.is_dir())

    def test_retiring_a_clean_shadow_removes_it(self):
        candidate, _ = shadow_candidate.provision(
            self.product, self.workspace, "0123456789abcdef")
        self.assertTrue(shadow_candidate.retire(candidate))
        self.assertFalse(candidate.exists())
        self.assertFalse(shadow_candidate.retire(candidate))

    def test_a_base_that_is_not_an_ancestor_is_refused(self):
        # A ref that merely lags the product is still an ancestor; the case
        # that has to be refused is a ref on a line the product does not
        # contain, which is what a re-anchored or foreign base looks like.
        _git(self.product, "checkout", "-q", "-b", "divergent")
        _git(self.product, "commit", "-q", "--allow-empty", "-m", "linea ajena")
        foreign = _git(self.product, "rev-parse", "HEAD").stdout.strip()
        _git(self.product, "checkout", "-q", "main")
        with self.assertRaises(shadow_candidate.ShadowError):
            shadow_candidate.provision(self.product, self.workspace,
                                       "0123456789abcdef", base_ref=foreign)


if __name__ == "__main__":
    unittest.main()
