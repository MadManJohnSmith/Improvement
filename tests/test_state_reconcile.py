"""Regression for the operator reconciliation of mode-state against the product.

C4, C5 and C6 are three ways the state can describe something the repository no
longer agrees with, and each of them was paid for by hand before: an integrated
head that an amend or a rebase erased, findings the ledger still calls OPEN
after their work item was VERIFIED, and an integrated candidate whose worktree
and branch stayed on disk. The reconciler asks git the same questions the
operator would ask, and every refusal has to leave the repository untouched.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import state_reconcile
import mode_lifecycle


def _git(path, *arguments):
    return subprocess.run(["git", "-C", str(path), *arguments], check=True,
                          capture_output=True, text=True)


class StateReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.session = root / "session"
        self.product = self.session / "Product"
        self.workspace = self.session / "Product-workspace"
        self.state = self.workspace / "mode-state"
        self.product.mkdir(parents=True)
        self.state.mkdir(parents=True)
        _git(self.product, "init", "-q", "-b", "main")
        _git(self.product, "config", "user.email", "operator@example.invalid")
        _git(self.product, "config", "user.name", "Operator")
        (self.product / "a.txt").write_text("one\n")
        _git(self.product, "add", "-A")
        _git(self.product, "commit", "-qm", "base")
        self.base = self._rev("HEAD")

    def _rev(self, revision="HEAD"):
        return subprocess.run(
            ["git", "-C", str(self.product), "rev-parse", revision],
            capture_output=True, text=True, check=True).stdout.strip()

    def _head_of(self, path):
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()

    def _write_state(self, candidate, items=(), findings=(), handoffs=(),
                     verifications=()):
        (self.state / "work-items.json").write_text(json.dumps(
            {"schema_version": 1, "candidate": candidate, "items": list(items)}))
        (self.state / "findings.jsonl").write_text("".join(
            json.dumps(record) + "\n" for record in findings))
        (self.state / "handoffs.jsonl").write_text("".join(
            json.dumps(record) + "\n" for record in handoffs))
        (self.state / "verification-results.jsonl").write_text("".join(
            json.dumps(record) + "\n" for record in verifications))

    def _integrated_candidate(self, branch="dsh/repair-0123456789abcdef",
                              path="Product-repair-0123456789abcdef"):
        return {"base_revision": self.base, "finding_ids_digest": "b" * 64,
                "path": path, "branch": branch, "head": self.base,
                "status": "INTEGRATED",
                "candidate_diff_digest": "c" * 64, "changed_paths": ["a.txt"]}

    def test_reconcile_names_the_findings_the_ledger_outgrew(self):
        """C5: 30 of the 42 open Syncify findings had a VERIFIED work item.

        The repair closes the finding; the ledger only reaches RESOLVED when a
        later audit sees it clean, so between the two the queue offers work that
        is already done. The view is derived and never rewrites the ledger.
        """
        self._write_state(
            None,
            items=[{"work_item_id": "W-01", "finding_id": "A-01",
                    "base_revision": self.base, "status": "VERIFIED"},
                   {"work_item_id": "W-02", "finding_id": "A-02",
                    "base_revision": self.base, "status": "PENDING"}],
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "HIGH", "summary": "Fixed", "status": "OPEN"},
                      {"finding_id": "A-02", "base_revision": self.base,
                       "severity": "LOW", "summary": "Pending", "status": "OPEN"},
                      {"finding_id": "A-03", "base_revision": self.base,
                       "severity": "LOW", "summary": "Closed", "status": "RESOLVED"}],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01", "A-02"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}])
        before = (self.state / "findings.jsonl").read_text()
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertEqual(report["closed_findings"], ["A-01"])
        self.assertEqual(report["uncovered_findings"], [])
        self.assertIsNone(report["candidate"])
        # The derived view is a view: it rewrites no ledger line, so a finding
        # the operator has not re-audited yet keeps saying what it said.
        self.assertEqual((self.state / "findings.jsonl").read_text(), before)
        self.assertIn('"status": "OPEN"', before)

    def test_reconcile_reports_an_integrated_head_that_history_erased(self):
        """C4: an amend or a rebase after integration left the record naming nothing."""
        self._write_state(self._integrated_candidate())
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertTrue(report["candidate"]["head_exists"])
        self.assertTrue(report["candidate"]["head_in_canonical"])

        (self.product / "a.txt").write_text("two\n")
        _git(self.product, "commit", "-q", "-a", "--amend", "-m", "amend")
        rewritten = state_reconcile.reconcile(self.product, self.workspace)
        # The amended commit survives as a dangling object, so existence is not
        # the signal: what matters is whether the recorded revision is still
        # part of the canonical branch the operator integrates into.
        self.assertTrue(rewritten["candidate"]["head_exists"])
        self.assertFalse(rewritten["candidate"]["head_in_canonical"])
        self.assertTrue(rewritten.get("integrated_head_rewritten"))

    def test_repoint_only_moves_onto_a_revision_the_canonical_branch_has(self):
        self._write_state(self._integrated_candidate())

        # Nothing moved: the recorded revision is still in the canonical
        # branch, so the record is exact and re-pointing it would be a lie.
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "sigue en la rama canónica"):
            state_reconcile.repoint(self.product, self.workspace, self.base)

        (self.product / "a.txt").write_text("two\n")
        _git(self.product, "commit", "-q", "-a", "--amend", "-m", "amend")
        new_head = self._rev()

        _git(self.product, "checkout", "-q", "--orphan", "side")
        _git(self.product, "rm", "-q", "-rf", ".")
        (self.product / "b.txt").write_text("side\n")
        _git(self.product, "add", "-A")
        _git(self.product, "commit", "-qm", "side")
        side = self._rev("HEAD")
        _git(self.product, "checkout", "-q", "main")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "no es ancestro"):
            state_reconcile.repoint(self.product, self.workspace, side)
        self.assertEqual(
            json.loads((self.state / "work-items.json").read_text())["candidate"]["head"],
            self.base)

        moved = state_reconcile.repoint(self.product, self.workspace, new_head)
        self.assertEqual((moved["from"], moved["to"]), (self.base, new_head))
        recorded = json.loads((self.state / "work-items.json").read_text())
        self.assertEqual(recorded["candidate"]["head"], new_head)
        receipt = json.loads(
            (self.state / "overflows.jsonl").read_text().splitlines()[0])
        self.assertEqual(receipt["reason"], "integrated-head-rewritten")
        self.assertEqual(state_reconcile.reconcile(
            self.product, self.workspace)["candidate"]["head_in_canonical"], True)

    def test_retire_refuses_legacy_worktree_even_after_integration(self):
        branch = "dsh/repair-0123456789abcdef"
        name = "Product-repair-0123456789abcdef"
        worktree = self.session / name
        _git(self.product, "worktree", "add", "-q", "-b", branch, str(worktree))
        (worktree / "a.txt").write_text("fixed\n")
        _git(worktree, "commit", "-q", "-a", "-m", "fix")
        _git(self.product, "merge", "-q", "--ff-only", branch)
        self._write_state(dict(self._integrated_candidate(),
                               head=self._rev(), base_revision=self._rev()))

        # Git status cannot inventory ignored content; a clean worktree is
        # therefore not a deletion authorization for the operator's files.
        _git(worktree, "config", "core.excludesFile", str(self.session / "ignore-patterns"))
        (self.session / "ignore-patterns").write_text("operator-notes\n")
        private = worktree / "operator-notes"
        private.write_text("material ajeno\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(worktree.exists())
        self.assertEqual(private.read_text(), "material ajeno\n")
        self.assertIn(
            branch,
            subprocess.run(["git", "-C", str(self.product), "branch", "--list"],
                           capture_output=True, text=True, check=True).stdout)
        self.assertTrue(_git(self.product, "worktree", "list", "--porcelain").stdout)

    def test_retire_refuses_an_unintegrated_or_dirty_candidate(self):
        branch = "dsh/repair-0123456789abcdef"
        name = "Product-repair-0123456789abcdef"
        _git(self.product, "worktree", "add", "-q", "-b", branch,
             str(self.session / name))
        candidate = self._integrated_candidate()

        # Committed in the candidate but never merged: removing the worktree
        # would delete work the canonical branch does not have.
        (self.session / name / "a.txt").write_text("fixed\n")
        _git(self.session / name, "commit", "-q", "-a", "-m", "fix")
        candidate["head"] = self._head_of(self.session / name)
        self._write_state(candidate)
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "no está en la rama canónica"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue((self.session / name).exists())

        # Uncommitted work in an otherwise integrated worktree is work too.
        _git(self.product, "merge", "-q", "--ff-only", branch)
        (self.session / name / "a.txt").write_text("still editing\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "cambios sin integrar"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue((self.session / name).exists())

        # A candidate that was never integrated is not retirable at all.
        self._write_state(dict(candidate, status="DIRTY"))
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "solo se retira una INTEGRATED"):
            state_reconcile.retire(self.product, self.workspace)

    def _shadow(self):
        """Provision through Host, then record its exact dirty patch in state."""
        host = mode_lifecycle.provision_repair(
            self.product, self.workspace, ["A-01"], declared_base=self.base)
        shadow = Path(host["path"])
        (shadow / "a.txt").write_text("fixed\n")
        raw = b"a.txt"
        data = b"fixed\n"
        digest = hashlib.sha256(len(raw).to_bytes(8, "big") + raw + b"F" +
                                len(data).to_bytes(8, "big") + data).hexdigest()
        record = {"base_revision": host["base_revision"],
                  "finding_ids_digest": host["finding_ids_digest"],
                  "path": f"{self.workspace.name}/candidates/{shadow.name}",
                  "branch": host["branch"], "head": host["head"],
                  "status": "INTEGRATED", "candidate_diff_digest": digest,
                  "changed_paths": ["a.txt"]}
        self._write_state(record)
        return shadow, record

    def test_shadow_retire_requires_exact_product_patch_and_receipt(self):
        """Exact integration evidence is not enough to delete a Host shadow.

        The patch is proven in the canonical tree, the receipt matches the
        state and the shadow is clean, and retirement still abstains: the
        deletion could not be made fail-closed. `git status` never inventories
        `.git/`, `skip-worktree`/`assume-unchanged` hide edits to tracked files
        from it, and the content comparison ran *before* the non-atomic
        `shutil.rmtree`, so private files inside the shadow's own `.git/` and
        any concurrent edit were deleted with no gate ever seeing them.
        """
        shadow, record = self._shadow()
        receipt = Path(self.workspace / f"{shadow.name}.receipt")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED.*integración exacta"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        # With *only* the recorded dirty patch, every gate passes. Even this
        # exact integration evidence must not authorize deletion.
        with self.assertRaisesRegex(
                state_reconcile.ReconcileError,
                r"ABSTAINED.*conjunto de contenido exclusivo.*manual"):
            state_reconcile.retire(self.product, self.workspace)
        # Additional content: an extra working file, an ignored one and a
        # private file inside the shadow's own `.git/`.
        (shadow / "operator-notes.txt").write_text("notas sin commitear\n")
        (shadow / ".gitignore").write_text("build.log\n")
        (shadow / "build.log").write_text("logs\n")
        (shadow / ".git" / "operator-notes").write_text("notas privadas en .git\n")
        before = {path: path.read_bytes()
                  for path in sorted(shadow.rglob("*"))
                  if path.is_file() and ".git/objects" not in str(path)}

        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)

        self.assertTrue(shadow.exists())
        self.assertTrue(receipt.exists())
        self.assertTrue(shadow.is_dir())
        self.assertTrue(shadow.joinpath("a.txt").is_file())
        self.assertEqual(shadow.joinpath("a.txt").read_bytes(), b"fixed\n")
        for path, content in before.items():
            self.assertTrue(path.exists(), f"{path} fue borrado")
            self.assertEqual(path.read_bytes(), content, f"{path} fue modificado")
        self.assertTrue(shadow.joinpath(".git", "operator-notes").is_file())
        self.assertEqual(
            shadow.joinpath(".git", "operator-notes").read_bytes(),
            b"notas privadas en .git\n")
        # The operator's integration is the only thing the product gained: the
        # shadow's own commit never entered the canonical history.
        self.assertEqual(_git(self.product, "rev-list", "--count", "HEAD").stdout.strip(),
                         "2")
        self.assertFalse(_git(self.product, "status", "--porcelain=v1").stdout)

    def test_shadow_retire_refuses_dirty_extra_clean_or_modified_product(self):
        shadow, record = self._shadow()
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        (shadow / "extra.txt").write_text("unintegrated\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        (shadow / "extra.txt").unlink()
        _git(shadow, "add", "a.txt")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        _git(shadow, "reset", "-q", "a.txt")
        (shadow / "a.txt").write_text("one\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        (shadow / "a.txt").write_text("another patch\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        (shadow / "a.txt").write_text("fixed\n")
        (self.product / "a.txt").write_text("local edit\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED.*producto"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())

    def test_shadow_retire_refuses_missing_or_foreign_receipt_and_symlinks(self):
        shadow, record = self._shadow()
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        receipt = self.workspace / f"{shadow.name}.receipt"
        original = receipt.read_text()
        receipt.unlink()
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        receipt.write_text(self.base + "\n" + "f" * 64 + "\n" + record["head"] + "\n")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "recibo Host"):
            state_reconcile.retire(self.product, self.workspace)
        receipt.unlink()
        receipt.symlink_to(shadow / "a.txt")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "enlace simbólico"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())
        receipt.unlink()
        receipt.write_text(original)
        (shadow / "other-link").symlink_to(self.product / "a.txt")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())

    def test_shadow_retire_never_adopts_a_legacy_worktree_or_foreign_git(self):
        shadow, record = self._shadow()
        branch = f"dsh/repair-{record['finding_ids_digest'][:16]}"
        legacy = self.session / f"{self.product.name}-repair-{record['finding_ids_digest'][:16]}"
        _git(self.product, "worktree", "add", "-q", "-b", branch, str(legacy))
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(legacy.exists())
        self.assertTrue(legacy.joinpath(".git").exists())
        self.assertTrue(shadow.exists())

    def test_shadow_retire_preserves_product_with_external_git_dir(self):
        external = self.session / "external-git"
        _git(self.product, "init", "-q", "--separate-git-dir", str(external))
        self.base = self._rev()
        shadow, record = self._shadow()
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(external.is_dir())
        self.assertTrue(shadow.exists())

    def test_bootstrap_state_retire_abstains_without_touching_either_tree(self):
        """The operator command exits 1 with the reason and deletes nothing."""
        shadow, record = self._shadow()
        (self.product / "a.txt").write_text("different\n")
        _git(self.product, "commit", "-qam", "not integrated")
        process = subprocess.run(
            ["/usr/bin/python3", "-B", str(ROOT / "scripts" / "bootstrap.py"),
             "state", "--project", str(self.product), "--retire"],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(process.returncode, 1)
        self.assertIn("ABSTAINED", process.stderr)
        self.assertTrue(shadow.exists())
        self.assertEqual((self.product / "a.txt").read_text(), "different\n")

    def test_shadow_retire_abstains_when_git_hangs(self):
        """Git that does not answer is a refusal, not a silent deletion."""
        shadow, record = self._shadow()
        with patch.object(state_reconcile.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("git", 120)):
            with self.assertRaisesRegex(state_reconcile.ReconcileError, "120s"):
                state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())

    def test_shadow_retire_refuses_a_declared_integration_it_cannot_prove(self):
        """A status that claims INTEGRATED without the patch proving it."""
        shadow, record = self._shadow()
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        (self.product / "a.txt").write_text("fixed\n")
        _git(self.product, "commit", "-qam", "integrated patch")
        # A body that followed the record verbatim would commit the shadow into
        # history, which is exactly what the shadow's contract forbids.
        self.assertFalse(shadow.joinpath(".git", "refs", "heads", "dsh").exists())
        # Even with the integration proven the shadow is not deleted, so its own
        # commit never reaches the canonical history: the base commit plus the
        # operator's integration, nothing else.
        with self.assertRaisesRegex(state_reconcile.ReconcileError, "ABSTAINED"):
            state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(shadow.exists())
        self.assertEqual(
            subprocess.run(["git", "-C", str(self.product), "rev-list", "--count", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip(), "2")

    def test_audit_scope_is_counted_from_the_handoff_id(self):
        """A complete audit that starts from the queue re-reports the queue.

        The distinction between observing first and verifying first is a claim
        in the prompt; putting it in the handoff id is what makes it countable
        afterwards, and a ledger that only ever says "audit-1" cannot say which
        kind of review produced it.
        """
        self._write_state(
            None,
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "LOW", "summary": "x", "status": "OPEN"}],
            handoffs=[{"handoff_id": "audit-complete-abcdef12-1", "base_revision": self.base,
                       "finding_ids": ["A-01"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."},
                      {"handoff_id": "audit-abcdef12-2", "base_revision": self.base,
                       "finding_ids": ["A-01"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."},
                      {"handoff_id": "repair-1", "base_revision": self.base,
                       "finding_ids": ["A-01"], "next_prompt": "Repara A-01; no publiques."}])
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertEqual(report["audit_scopes"], {"complete": 1, "incremental": 1})
        self.assertEqual(report["closed_findings"], [])
        self.assertEqual(report["uncovered_findings"], [])

    def test_anchor_ratio_is_reported_without_touching_the_ledger(self):
        self._write_state(
            None,
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "HIGH", "summary": "x", "status": "OPEN",
                       "evidence": {"path": "a.txt", "excerpt": "one", "line": 1,
                                    "located": True}},
                      {"finding_id": "A-02", "base_revision": self.base,
                       "severity": "HIGH", "summary": "Architecture", "status": "OPEN"}],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01", "A-02"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}])
        before = (self.state / "findings.jsonl").read_text()
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertEqual(report["anchors"], {"anchored": 1, "unanchored": 1})
        self.assertEqual((self.state / "findings.jsonl").read_text(), before)

    def test_what_the_framework_remembers_is_visible_and_consistent(self):
        """The memory existed, was correct, and nothing showed it.

        `episodes.py` had a ledger, an index and seventeen green tests, and no
        operator-facing way to ask what the framework remembered about their
        project — so "la memoria se aplica también a sí misma" was a line in
        the README with no way to check it. The report carries the counts, and
        carries the drift check too: a finding claiming an episode the ledger
        no longer holds is two files disagreeing, and a repeat nobody can trace
        is not a repeat the memory proved.
        """
        import episodes

        self._write_state(
            None,
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "HIGH", "summary": "x", "status": "OPEN",
                       "evidence": {"path": "src/a.py", "excerpt": "token = 1",
                                    "line": 1, "located": True,
                                    "prior_episode": {"unit": "unit-1",
                                                      "evidence": "v.jsonl#unit-1",
                                                      "repair": "borrar la cache"}}},
                      {"finding_id": "A-02", "base_revision": self.base,
                       "severity": "HIGH", "summary": "y", "status": "OPEN",
                       "evidence": {"path": "src/b.py", "excerpt": "other",
                                    "line": 2, "located": True,
                                    "prior_episode": {"unit": "fantasma",
                                                      "evidence": None,
                                                      "repair": None}}}],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01", "A-02"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}])
        # Nothing closed yet: an empty memory is a measurement, not a failure.
        empty = state_reconcile.memory(self.workspace)
        self.assertEqual(empty["episodes"], 0)
        self.assertEqual(empty["units"], [])

        episodes.record(self.workspace, unit="unit-1", path="src/a.py",
                        excerpt="token = 1", verdict="PASS",
                        evidence="verification.jsonl#unit-1",
                        repair="borrar la cache")
        report = state_reconcile.memory(self.workspace)
        self.assertEqual(report["episodes"], 1)
        self.assertEqual(report["signatures"], 1)
        self.assertEqual(report["units"], ["unit-1"])
        self.assertGreater(report["ledger_bytes"], 0)
        # A-02 claims an episode the ledger never held. Reporting it is the
        # whole point: a drift the report hid would be a memory that lies.
        self.assertEqual(report["unknown_claimed_units"], ["fantasma"])

    def test_the_derived_verdict_is_computed_somewhere_at_all(self):
        """Three documents promised a derived verdict that nothing produced.

        The plugin stores one verification record per entrypoint and says, in
        its own comment, that PASS-with-BLOCKED is a partial result "and the
        Host derives it". The contract declares
        `worst-result-per-finding-and-candidate-partial-is-derived-not-written`
        and the persona tells the mode the name is derived from the records.
        `stack.derived_verdicts` existed, was tested, and was called by nothing
        outside `tests/`. A finding whose tests passed while its linter could
        not run therefore had no verdict anywhere in this framework: not in the
        state, not in the report, not anywhere.

        The derivation happens at read time and is never written back, because
        D6's decision was that `PARTIAL` is derived and the persisted enum stays
        closed. What the report adds is `partial`, which the bare verdict threw
        away — `BLOCKED` from one PASS and one BLOCKED is progress, `BLOCKED`
        from a single BLOCKED is nothing having run.
        """
        head = "c" * 40

        def result(finding, command, verdict):
            return {"finding_id": finding, "candidate_head": head, "command": command,
                    "candidate_diff_digest": "b" * 64, "result": verdict}

        self._write_state(
            None,
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "HIGH", "summary": "x", "status": "OPEN"},
                      {"finding_id": "A-02", "base_revision": self.base,
                       "severity": "HIGH", "summary": "y", "status": "OPEN"},
                      {"finding_id": "A-03", "base_revision": self.base,
                       "severity": "HIGH", "summary": "z", "status": "OPEN"},
                      {"finding_id": "A-04", "base_revision": self.base,
                       "severity": "HIGH", "summary": "w", "status": "OPEN"}],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01", "A-02", "A-03", "A-04"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}],
            verifications=[result("A-01", "pytest", "PASS"),
                           result("A-02", "pytest", "PASS"),
                           result("A-02", "ruff", "BLOCKED"),
                           result("A-03", "ruff", "BLOCKED"),
                           result("A-04", "pytest", "FAIL")])
        before = (self.state / "verification-results.jsonl").read_text()
        report = state_reconcile.reconcile(self.product, self.workspace)
        verdicts = report["verifications"]

        self.assertEqual(verdicts["counts"],
                         {"PASS": 1, "BLOCKED": 1, "FAIL": 1, "PARTIAL": 1})
        self.assertEqual(
            {(entry["finding_id"], entry["verdict"]) for entry in verdicts["unverified"]},
            {("A-02", "PARTIAL"), ("A-03", "BLOCKED"), ("A-04", "FAIL")})
        partial = next(e for e in verdicts["unverified"] if e["finding_id"] == "A-02")
        blocked = next(e for e in verdicts["unverified"] if e["finding_id"] == "A-03")
        self.assertEqual(partial["entries"], 2)
        self.assertEqual(blocked["entries"], 1)
        # Derived, not written: the record the mode persisted is untouched.
        self.assertEqual((self.state / "verification-results.jsonl").read_text(), before)

    def test_defects_the_memory_had_closed_are_reported_as_repeats(self):
        """A repeat is not a failure of the ledger; it is a failed prevention.

        The write tool stamps `prior_episode` on a finding whose fingerprint the
        episodic memory already closed by a verified repair. Counting those OPEN
        findings is the only place a prevention that did not work becomes
        visible, and it is countable without reading the product — the same
        property `anchors` has. A finding the ledger already resolved is not a
        repeat anyone has to look at, so the count is over OPEN ones only.
        """
        prior = {"unit": "U-7", "evidence": "verification.jsonl#U-7",
                 "repair": "Validate the payload against the route schema"}
        self._write_state(
            None,
            findings=[{"finding_id": "A-01", "base_revision": self.base,
                       "severity": "HIGH", "summary": "x", "status": "OPEN",
                       "evidence": {"path": "a.txt", "excerpt": "one", "line": 1,
                                    "located": True, "prior_episode": prior}},
                      {"finding_id": "A-02", "base_revision": self.base,
                       "severity": "HIGH", "summary": "y", "status": "RESOLVED",
                       "evidence": {"path": "b.txt", "excerpt": "two", "line": 3,
                                    "located": True, "prior_episode": prior}},
                      {"finding_id": "A-03", "base_revision": self.base,
                       "severity": "HIGH", "summary": "z", "status": "OPEN",
                       "evidence": {"path": "c.txt", "excerpt": "three", "line": 5,
                                    "located": True}}],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01", "A-02", "A-03"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}])
        before = (self.state / "findings.jsonl").read_text()
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertEqual(report["repeats"], {"open": 1, "prior_units": ["U-7"]})
        self.assertEqual((self.state / "findings.jsonl").read_text(), before)

    def test_uncovered_findings_name_what_no_handoff_ever_took(self):
        self._write_state(
            None,
            items=[{"work_item_id": f"W-{index:02d}", "finding_id": f"A-{index:02d}",
                    "base_revision": self.base, "status": "PENDING"}
                   for index in range(1, 4)],
            findings=[{"finding_id": f"A-{index:02d}", "base_revision": self.base,
                       "severity": "LOW", "summary": "x", "status": "OPEN"}
                      for index in range(1, 4)],
            handoffs=[{"handoff_id": "audit-1", "base_revision": self.base,
                       "finding_ids": ["A-01"],
                       "next_prompt": "Repara los hallazgos de la auditoría; no publiques."}])
        report = state_reconcile.reconcile(self.product, self.workspace)
        self.assertEqual(report["uncovered_findings"], ["A-02", "A-03"])

    def test_shadow_status_abstains_when_the_cone_hides_tracked_content(self):
        """A cone marks tracked paths skip-worktree; status then reports none of them.

        The inventory below the guard is a `git status` of the shadow, and a
        cone prunes that inventory to the coned directories: every tracked path
        outside the cone is marked `S` and stops being reported at all -- so a
        shadow whose tracked content was replaced, or whose out-of-cone files
        were deleted by hand, reports clean and would be deleted by a call that
        asked nothing else. The guard is the only thing that sees it.
        """
        shadow, record = self._shadow()
        (shadow / "outside.txt").write_text("one\n")
        (shadow / "outside").mkdir()
        (shadow / "outside" / "nested.txt").write_text("tracked\n")
        _git(shadow, "add", "-A")
        _git(shadow, "commit", "-qm", "tracked content outside the cone")
        _git(shadow, "sparse-checkout", "set", "--cone", "nested-nonexistent")
        # The inventory alone is blind: the paths stay tracked and marked
        # skip-worktree, and `git status` says nothing about either of them.
        plain = _git(shadow, "status", "--porcelain=v1", "--untracked-files=all",
                     "--ignored=matching").stdout
        self.assertNotIn("outside.txt", plain)
        self.assertNotIn("outside/nested.txt", plain)
        self.assertEqual(plain.strip(), "")
        self.assertIn("S outside/nested.txt", _git(shadow, "ls-files", "-t").stdout)
        with self.assertRaisesRegex(state_reconcile.ReconcileError,
                                    "checkout disperso"):
            state_reconcile._shadow_status(shadow)
        self.assertTrue((shadow / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()