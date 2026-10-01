"""Regression for the operator reconciliation of mode-state against the product.

C4, C5 and C6 are three ways the state can describe something the repository no
longer agrees with, and each of them was paid for by hand before: an integrated
head that an amend or a rebase erased, findings the ledger still calls OPEN
after their work item was VERIFIED, and an integrated candidate whose worktree
and branch stayed on disk. The reconciler asks git the same questions the
operator would ask, and every refusal has to leave the repository untouched.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import state_reconcile


def _git(path, *arguments):
    subprocess.run(["git", "-C", str(path), *arguments], check=True,
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

    def _write_state(self, candidate, items=(), findings=(), handoffs=()):
        (self.state / "work-items.json").write_text(json.dumps(
            {"schema_version": 1, "candidate": candidate, "items": list(items)}))
        (self.state / "findings.jsonl").write_text("".join(
            json.dumps(record) + "\n" for record in findings))
        (self.state / "handoffs.jsonl").write_text("".join(
            json.dumps(record) + "\n" for record in handoffs))

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

    def test_retire_removes_only_provably_integrated_work(self):
        branch = "dsh/repair-0123456789abcdef"
        name = "Product-repair-0123456789abcdef"
        _git(self.product, "worktree", "add", "-q", "-b", branch,
             str(self.session / name))
        (self.session / name / "a.txt").write_text("fixed\n")
        _git(self.session / name, "commit", "-q", "-a", "-m", "fix")
        _git(self.product, "merge", "-q", "--ff-only", branch)
        # The operator records INTEGRATED naming the revision now in main.
        self._write_state(dict(self._integrated_candidate(),
                               head=self._rev(), base_revision=self._rev()))

        result = state_reconcile.retire(self.product, self.workspace)
        self.assertTrue(result["retired"])
        self.assertFalse(result["already"])
        self.assertFalse((self.session / name).exists())
        self.assertNotIn(
            branch,
            subprocess.run(["git", "-C", str(self.product), "branch", "--list"],
                           capture_output=True, text=True, check=True).stdout)
        # Idempotent: a second run says so instead of failing on what it did.
        self.assertTrue(state_reconcile.retire(self.product, self.workspace)["already"])

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


if __name__ == "__main__":
    unittest.main()