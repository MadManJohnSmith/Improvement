import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mode_lifecycle
from mode_lifecycle import (AUDIT_NEXT_PROMPT, BYTE_LIMITS,
                            LEGACY_FILE_BYTE_LIMIT,
                            LEGACY_TOTAL_BYTE_LIMIT, LIMITS, RECORD_BYTE_LIMIT,
                            audit_count_command, compact_records, initialize_state,
                            repair_candidate_diff_command,
                            repair_provision_command, repair_reconcile_command,
                            repair_recording_command, repair_resume_command,
                            startup_check, state_schema)

# A product root with a space in it. Every central command passes it to `git -C`
# and to `realpath`, so a fixture named "Product" proves nothing about quoting:
# an unquoted `$product` splits, the path is not a repository, and the turn is
# retained for a reason the reader cannot see.
PRODUCT = "My Product"
# generation-manifest context_policy.support_file_max_bytes: the ceiling the
# graph and context_budget layers apply to every artifact that is not a SKILL.md.
SUPPORT_FILE_MAX_BYTES = 25600


def _placeholders(command):
    """Every unsubstituted token the person would have to replace in a command."""
    return set(re.findall(r"<[a-z][a-z0-9-]*>", command))


class ModeLifecycleTests(unittest.TestCase):
    def test_startup_check_is_exact_and_fails_closed_as_one_test(self):
        layout = {"session_root": "Syncify", "product_root": "Syncify",
                  "workspace_root": "Syncify-workspace"}
        command = startup_check(layout)
        self.assertEqual(
            command,
            'set -eu; pwd; test "$(basename "$PWD")" = Syncify '
            '-a -d ./Syncify -a -d ./Syncify-workspace; '
            "printf '__IMPROVEMENT_LAYOUT_OK__\\n'")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "Syncify"
            wrong = root / "wrong"
            session.mkdir()
            wrong.mkdir()
            for cwd in (wrong, session):
                (cwd / "Syncify").mkdir()
                (cwd / "Syncify-workspace").mkdir()
            wrong_cwd = subprocess.run(command, cwd=wrong, shell=True,
                                       capture_output=True, text=True)
            self.assertNotEqual(wrong_cwd.returncode, 0)
            self.assertNotIn(mode_lifecycle.SUCCESS_SENTINEL, wrong_cwd.stdout)
            (session / "Syncify").rmdir()
            missing_product = subprocess.run(command, cwd=session, shell=True,
                                             capture_output=True, text=True)
            self.assertNotEqual(missing_product.returncode, 0)
            self.assertNotIn(mode_lifecycle.SUCCESS_SENTINEL, missing_product.stdout)
            (session / "Syncify").mkdir()
            (session / "Syncify-workspace").rmdir()
            missing_workspace = subprocess.run(command, cwd=session, shell=True,
                                               capture_output=True, text=True)
            self.assertNotEqual(missing_workspace.returncode, 0)
            self.assertNotIn(mode_lifecycle.SUCCESS_SENTINEL, missing_workspace.stdout)
            (session / "Syncify-workspace").mkdir()
            result = subprocess.run(command, cwd=session, shell=True,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.splitlines(), [
                str(session), mode_lifecycle.SUCCESS_SENTINEL])

    def test_audit_count_command_derives_the_count_from_the_state(self):
        """`persisted_count` is copied from the file, never from memory.

        The count the auditor reports is the only number a reader has to decide
        whether a turn did anything, so the command has to derive it from what
        landed and refuse when the handoff and the findings disagree. The three
        refusals are the ones a turn actually hits: an OPEN finding nobody
        handed off, no audit handoff at all, and a handoff for another base.
        """
        layout = {"session_root": "Syncify", "product_root": "Syncify",
                  "workspace_root": "Syncify-workspace",
                  "state_root": "Syncify-workspace/mode-state"}
        base = "a" * 40
        command = audit_count_command(layout).replace("<base-revision>", base)
        self.assertEqual(_placeholders(command), set())

        def write(name, records):
            path = Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                   for record in records), encoding="utf-8")

        def finding(finding_id, status="OPEN", revision=base):
            return {"finding_id": finding_id, "base_revision": revision,
                    "severity": "HIGH", "summary": "Missing validation",
                    "status": status}

        def handoff(ids, revision=base, prompt=AUDIT_NEXT_PROMPT):
            return {"handoff_id": "audit-1", "base_revision": revision,
                    "finding_ids": ids, "next_prompt": prompt}

        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "Syncify"
            state = session / "Syncify-workspace" / "mode-state"
            state.mkdir(parents=True)
            run = lambda: subprocess.run(command, cwd=session, shell=True,
                                         capture_output=True, text=True)

            write(state / "findings.jsonl", [finding("A-01"), finding("A-02"),
                                             finding("A-03", status="RESOLVED")])
            write(state / "handoffs.jsonl", [handoff(["A-01", "A-02"])])
            complete = run()
            self.assertEqual(complete.returncode, 0, complete.stderr)
            self.assertEqual(complete.stdout.splitlines(), [
                "__IMPROVEMENT_AUDIT_COUNT__ 2",
                "__IMPROVEMENT_AUDIT_IDS__ A-01 A-02"])

            write(state / "findings.jsonl", [finding("A-01"), finding("A-02"),
                                             finding("A-03", status="RESOLVED"),
                                             finding("A-04")])
            uncovered = run()
            self.assertNotEqual(uncovered.returncode, 0)
            self.assertNotIn("__IMPROVEMENT_AUDIT_COUNT__", uncovered.stdout)

            write(state / "handoffs.jsonl", [])
            missing_handoff = run()
            self.assertNotEqual(missing_handoff.returncode, 0)
            self.assertNotIn("__IMPROVEMENT_AUDIT_COUNT__", missing_handoff.stdout)

            write(state / "findings.jsonl", [finding("A-01"), finding("A-02"),
                                             finding("A-03", status="RESOLVED")])
            write(state / "handoffs.jsonl", [handoff(["A-01"], revision="b" * 40)])
            other_base = run()
            self.assertNotEqual(other_base.returncode, 0)
            self.assertNotIn("__IMPROVEMENT_AUDIT_COUNT__", other_base.stdout)

    def test_auditor_expected_lifecycle_keeps_session_cwd_for_all_bash_calls(self):
        layout = {"session_root": "parent", "product_root": "Syncify",
                  "workspace_root": "Syncify-workspace",
                  "state_root": "Syncify-workspace/mode-state"}
        auditor = mode_lifecycle.expected_lifecycle("auditor", layout)
        repair = mode_lifecycle.expected_lifecycle("continuous-repair", layout)
        self.assertEqual(auditor["tool_policy"]["bash_workdir"],
                         "session-cwd-only-all-calls")
        self.assertEqual(auditor["tool_policy"]["bash"], "read-only")
        self.assertNotIn("bash_workdir", repair["tool_policy"])
        self.assertEqual(repair["tool_policy"]["bash"],
                         "code-changes-require-workdir-exact-candidate")
        candidate = repair["repair_candidate"]
        self.assertEqual(candidate["candidate_root"],
                         "${session-cwd}/<workspace>/candidates/repair-<digest16>")
        self.assertEqual(candidate["candidate_workdir"],
                         "Syncify-repair-<digest16>")
        self.assertEqual(candidate["provision_workdir"], "omitted-session-cwd")
        self.assertEqual(candidate["provision_command"],
                         repair_provision_command(layout))
        self.assertEqual(candidate["unrelated_candidates"], "ignore-preserve")
        self.assertEqual(candidate["worktree_list_scope"],
                         "target-path-and-target-branch-only")
        self.assertEqual(candidate["resume_policy"], "exact-recorded-only")
        self.assertEqual(candidate["resume_statuses"],
                         ["DIRTY", "RETAINED-pending-verification"])
        self.assertEqual(candidate["unrecorded_dirty_target"],
                         "RETAINED-never-adopted")
        self.assertEqual(
            candidate["interrupted_turn_recovery"],
            "recorded-PROVISIONED-target-may-become-DIRTY-by-recording-command")
        self.assertTrue(candidate["record_before_first_edit"])
        self.assertEqual(candidate["record_statuses"], ["PROVISIONED", "DIRTY"])
        self.assertEqual(candidate["recording_command"],
                         repair_recording_command(layout))
        self.assertEqual(candidate["reconcile_command"],
                         repair_reconcile_command(layout))
        self.assertEqual(candidate["stale_record_policy"],
                         "reconcile-then-resume")
        self.assertEqual(candidate["stale_base_policy"],
                         "re-anchor-when-declared-base-is-ancestor-of-clean-head")
        self.assertIn("candidate-diff-nonempty",
                      candidate["stale_record_precondition"])
        self.assertEqual(candidate["candidate_diff_command"],
                         repair_candidate_diff_command(layout))
        self.assertEqual(candidate["resume_command"], repair_resume_command(layout))

    def _provision_fixture(self, root):
        session = root / "common-parent"
        product = session / PRODUCT
        workspace = session / f"{PRODUCT}-workspace"
        product.mkdir(parents=True)
        workspace.mkdir()
        subprocess.run(["git", "init", "-q", str(product)], check=True)
        (product / "tracked.txt").write_text("base\n")
        subprocess.run(["git", "-C", str(product), "add", "tracked.txt"], check=True)
        subprocess.run([
            "git", "-C", str(product), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "base",
        ], check=True)
        base = subprocess.check_output(
            ["git", "-C", str(product), "rev-parse", "HEAD"], text=True).strip()
        layout = {"session_root": session.name, "product_root": product.name,
                  "workspace_root": workspace.name,
                  "state_root": f"{workspace.name}/mode-state"}
        return session, product, layout, base

    def _candidate_name(self, digest):
        return f"{PRODUCT}-repair-{digest}"

    def _candidate(self, session, digest):
        return session / self._candidate_name(digest)

    def _run_command(self, template, session, layout, base,
                     digest="0123456789abcdef", diff_digest=None, declared=None):
        command = template(layout).replace(
            "<digest16>", digest).replace("<full-base>", base).replace(
                "<declared-base>", base if declared is None else declared)
        if diff_digest is not None:
            command = command.replace("<candidate-diff-digest>", diff_digest)
        return subprocess.run(command, cwd=session, shell=True,
                              capture_output=True, text=True)

    def _run_provision(self, session, layout, base, digest="0123456789abcdef",
                       declared=None):
        return self._run_command(repair_provision_command, session, layout, base,
                                 digest, declared=declared)
    def _capture_diff(self, session, layout, base, digest):
        result = self._run_command(
            repair_candidate_diff_command, session, layout, base, digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        marker, digest_value, paths = result.stdout.strip().split(" ", 2)
        self.assertEqual(marker, "__IMPROVEMENT_CANDIDATE_DIFF__")
        return digest_value, json.loads(paths)

    def _run_resume(self, session, layout, base, digest, diff_digest):
        return self._run_command(
            repair_resume_command, session, layout, base, digest, diff_digest)

    def _run_record(self, session, layout, base, digest, finding_digest=None):
        command = repair_recording_command(layout).replace(
            "<digest16>", digest).replace("<full-base>", base)
        command = command.replace(
            "<finding-ids-digest>", finding_digest or digest + "0" * 48)
        return subprocess.run(command, cwd=session, shell=True,
                              capture_output=True, text=True)

    def _read_record_evidence(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        marker, _, payload = result.stdout.strip().partition(" ")
        self.assertIn(marker, ("__IMPROVEMENT_CANDIDATE_RECORD__",
                               "__IMPROVEMENT_CANDIDATE_RECONCILE__"))
        return json.loads(payload)

    def test_repair_claims_candidate_before_first_edit_and_recovers_interrupted_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "5a5a5a5a5a5a5a5a"
            self.assertEqual(self._run_provision(
                session, layout, base, digest).returncode, 0)
            candidate = session / self._candidate_name(digest)

            claimed = self._read_record_evidence(
                self._run_record(session, layout, base, digest))
            self.assertEqual(claimed, {
                "base_revision": base,
                "finding_ids_digest": digest + "0" * 48,
                "path": self._candidate_name(digest),
                "branch": f"dsh/repair-{digest}",
                "head": base,
                "status": "PROVISIONED",
            })

            (candidate / "tracked.txt").write_bytes(b"interrupted repair bytes\n")
            recovered = self._read_record_evidence(
                self._run_record(session, layout, base, digest))
            self.assertEqual(recovered["status"], "DIRTY")
            self.assertEqual(recovered["changed_paths"], ["tracked.txt"])
            self.assertEqual(recovered["path"], self._candidate_name(digest))
            self.assertEqual(recovered["head"], base)
            self.assertEqual(recovered["base_revision"], base)
            self.assertEqual(recovered["finding_ids_digest"], digest + "0" * 48)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(candidate), "status", "--porcelain=v1"],
                    text=True), " M tracked.txt\n")
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(product), "status", "--porcelain=v1"], text=True), "")

            resumed = self._run_resume(session, layout, base, digest,
                                       recovered["candidate_diff_digest"])
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual((candidate / "tracked.txt").read_bytes(),
                             b"interrupted repair bytes\n")

    def test_repair_recording_command_fails_closed_outside_recorded_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "6b6b6b6b6b6b6b6b"
            cases = {"missing": base, "stale-base": "0" * 40}
            for mutation, base_value in cases.items():
                with self.subTest(mutation=mutation):
                    result = self._run_record(session, layout, base_value, digest)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(subprocess.check_output(
                        ["git", "-C", str(product), "status", "--porcelain=v1"],
                        text=True), "")

            with self.subTest(mutation="unregistered-target"):
                candidate = session / self._candidate_name(digest)
                candidate.mkdir()
                result = self._run_record(session, layout, base, digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(candidate.joinpath("tracked.txt").exists())

    def test_recording_command_emits_the_exact_persistable_candidate_object(self):
        """Regresión RehabWeb: el objeto emitido se persiste verbatim, sin ensamblado.

        El comando anterior imprimía una línea de 5 campos con ruta absoluta que
        ningún modo podía persistir sin transformarla a mano (ahí nacían los
        campos extra y las rutas absolutas que el preflight descartaba).
        """
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "9d9d9d9d9d9d9d9d"
            self.assertEqual(self._run_provision(
                session, layout, base, digest).returncode, 0)
            candidate_spec = state_schema()["files"]["work-items.json"]["candidate"]

            claimed = self._read_record_evidence(
                self._run_record(session, layout, base, digest))
            mode_lifecycle._valid(claimed, candidate_spec, "work-items.json.candidate")
            self.assertEqual(claimed["path"], self._candidate_name(digest))
            self.assertEqual(set(claimed), {
                "base_revision", "finding_ids_digest", "path", "branch",
                "head", "status"})

            (session / self._candidate_name(digest) / "tracked.txt").write_bytes(
                b"dirty\n")
            dirty = self._read_record_evidence(
                self._run_record(session, layout, base, digest))
            mode_lifecycle._valid(dirty, candidate_spec, "work-items.json.candidate")
            self.assertEqual(set(dirty), {
                "base_revision", "finding_ids_digest", "path", "branch",
                "head", "status", "candidate_diff_digest", "changed_paths"})

            # Lo que un modo escribía a mano queda fuera del contrato:
            with self.assertRaises(ValueError):
                mode_lifecycle._valid({**dirty, "extra_field": "x"},
                                      candidate_spec, "extra-field")
            with self.assertRaises(ValueError):
                mode_lifecycle._valid(
                    {**claimed, "path": str(self._candidate(session, digest))},
                    candidate_spec, "absolute-path")

    def test_preflight_drops_a_pass_that_did_not_verify_the_registered_candidate(self):
        """IMP-AUD-008: un PASS tiene que nombrar el árbol que verificó.

        El contrato prohíbe hacer commit de una candidata, así que el árbol
        verificado suele ser un worktree DIRTY cuyo HEAD sigue siendo su base y
        el arreglo vive en el diff sin commitear. `candidate_head` no lo
        distingue de la revisión anterior al arreglo, y medido en el self-test
        los siete registros llevaban dos cabezas, ambas anteriores al cambio.
        El digest del diff es la única huella del árbol real.
        """
        descriptor = {"schema_version": 1, "project_id": "p",
                      "product_root": "Product",
                      "state_root": "Product-workspace/mode-state"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            base = "a" * 40
            diff = "b" * 64
            candidate = {"base_revision": base, "finding_ids_digest": "c" * 64,
                         "path": "Product-repair-" + "d" * 16,
                         "branch": "dsh/repair-" + "d" * 16,
                         "head": base, "status": "DIRTY",
                         "candidate_diff_digest": diff,
                         "changed_paths": ["lib/example.py"]}
            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1, "candidate": candidate,
                "items": [{"work_item_id": "W-01", "finding_id": "A-01",
                           "base_revision": base, "status": "VERIFIED"}],
            }) + "\n")
            record = {"finding_id": "A-01", "candidate_head": base,
                      "candidate_diff_digest": diff, "result": "PASS",
                      "command": "pytest"}
            (state / "verification-results.jsonl").write_text(
                json.dumps(record) + "\n")

            # The record names another tree: it is evidence about something else.
            (state / "verification-results.jsonl").write_text(
                json.dumps({**record, "candidate_diff_digest": "e" * 64}) + "\n")
            report = initialize_state(state, descriptor, root / "archive")
            reasons = {note["reason"] for note in report["dropped"]}
            self.assertIn("verification-of-another-candidate", reasons)
            self.assertEqual(
                (state / "verification-results.jsonl").read_text(), "")

            # The record names the registered candidate: it stays.
            (state / "verification-results.jsonl").write_text(
                json.dumps(record) + "\n")
            report = initialize_state(state, descriptor, root / "archive")
            self.assertEqual(report["dropped"], [])
            kept = [json.loads(line) for line in
                    (state / "verification-results.jsonl").read_text().splitlines()
                    if line.strip()]
            self.assertEqual(kept, [record])

    def test_initialize_state_report_names_every_discard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            base = "a" * 40
            good_finding = {"finding_id": "A-01", "base_revision": base,
                            "severity": "HIGH", "summary": "s", "status": "OPEN"}
            (state / "findings.jsonl").write_text("\n".join([
                json.dumps(good_finding),
                "x" * (RECORD_BYTE_LIMIT + 1),
                "not-json",
                json.dumps({**good_finding, "finding_id": "A-02", "extra": 1}),
            ]) + "\n")
            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1,
                "candidate": {"base_revision": base,
                              "finding_ids_digest": "b" * 64,
                              "path": "/abs/Product-repair-" + "c" * 16,
                              "extra_field": 1,
                              "branch": "dsh/repair-" + "c" * 16,
                              "head": base, "status": "PROVISIONED"},
                "items": [{"work_item_id": "W-01", "finding_id": "A-01",
                           "base_revision": base, "status": "PENDING"},
                          {"work_item_id": "W-bad", "finding_id": "A-01",
                           "base_revision": base, "status": "NOT-A-STATUS"}],
            }) + "\n")
            (state / "overflows.jsonl").write_text(json.dumps(
                {"overflow_id": "OV-01", "file": "handoffs.jsonl",
                 "reason": "limit-overflow",
                 "dropped_records": ["audit-3"]}) + "\n")
            report = initialize_state(
                state, {"schema_version": 1, "project_id": "p",
                        "product_root": "Product",
                        "state_root": "Product-workspace/mode-state"},
                root / "archive")

            by_file = {note["file"]: note for note in report["dropped"]}
            self.assertEqual(by_file["findings.jsonl"]["reason"],
                             "incompatible-records")
            self.assertEqual(
                len(by_file["findings.jsonl"]["dropped_records"]), 3)
            self.assertTrue(any("A-02" in name
                                for name in by_file["findings.jsonl"]["dropped_records"]))
            self.assertEqual(by_file["work-items.json"]["dropped_records"],
                             ["W-bad", "candidate:/abs/Product-repair-" + "c" * 16])
            self.assertNotIn("overflows.jsonl", by_file)
            migrated = json.loads((state / "overflows.jsonl").read_text())
            self.assertEqual(migrated["overflow_id"], "OV-01")
            self.assertIsNotNone(report["archive"])

    def test_preflight_keeps_legacy_findings_and_activates_anchored_ones(self):
        """The anchor is added without touching any state that already exists.

        Every campaign so far wrote findings with five fields and the evidence
        buried in `summary`. Requiring an anchor in the schema would make the
        preflight archive all of it — a loss the framework never performs on
        historical evidence — so the field is optional: an unanchored legacy
        record stays exactly as it was, a well-formed anchor survives, and only
        a malformed one is dropped, with the receipt naming it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            base = "a" * 40
            legacy = {"finding_id": "A-01", "base_revision": base,
                      "severity": "HIGH", "summary": "Missing validation at src/api.py:42",
                      "status": "OPEN"}
            anchored = {**legacy, "finding_id": "A-02", "evidence": {
                "path": "src/api.py", "excerpt": "def create_user(payload):",
                "line": 42, "located": True}}
            malformed = {**legacy, "finding_id": "A-03", "evidence": {
                "path": "src/api.py", "excerpt": "def other():", "confidence": "alta"}}
            truncated = {**legacy, "finding_id": "A-04", "evidence": {
                "path": "src/api.py", "excerpt": "def third():", "line": 0, "located": True}}
            (state / "findings.jsonl").write_text("\n".join(
                json.dumps(record, ensure_ascii=False)
                for record in (legacy, anchored, malformed, truncated)) + "\n")
            report = initialize_state(
                state, {"schema_version": 1, "project_id": "p",
                        "product_root": "Product",
                        "state_root": "Product-workspace/mode-state"},
                root / "archive")

            active = [json.loads(line) for line in
                      (state / "findings.jsonl").read_text().splitlines() if line.strip()]
            self.assertEqual([record["finding_id"] for record in active],
                             ["A-01", "A-02"])
            self.assertNotIn("evidence", active[0])
            self.assertEqual(active[1]["evidence"]["line"], 42)
            self.assertIs(active[1]["evidence"]["located"], True)
            dropped = report["dropped"][0]["dropped_records"]
            self.assertTrue(any("A-03" in name for name in dropped))
            self.assertTrue(any("A-04" in name for name in dropped))

    def test_rich_finding_fields_are_optional_for_existing_state(self):
        """Adding cause, prevention and fingerprint must not touch old records.

        The four campaigns wrote five fields with the evidence in prose. If the
        preflight required the new fields it would archive every one of those
        records, so the fields are optional: a legacy finding stays exactly as
        it was, a well-formed rich finding survives, and a malformed one is
        dropped with a receipt naming it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            base = "a" * 40
            legacy = {"finding_id": "A-01", "base_revision": base,
                      "severity": "HIGH", "summary": "Missing validation", "status": "OPEN"}
            rich = {**legacy, "finding_id": "A-02", "cause": "trusts the body",
                    "prevention": "schema check",
                    "evidence": {"path": "src/api.py", "excerpt": "def create_user(payload):",
                                 "fingerprint": "d" * 64, "line": 42, "located": True}}
            bad_cause = {**rich, "finding_id": "A-03", "cause": "x" * 257}
            bad_fingerprint = {**rich, "finding_id": "A-04", "evidence": {
                **rich["evidence"], "fingerprint": "not-a-digest"}}
            (state / "findings.jsonl").write_text("\n".join(
                json.dumps(record, ensure_ascii=False)
                for record in (legacy, rich, bad_cause, bad_fingerprint)) + "\n")
            report = initialize_state(
                state, {"schema_version": 1, "project_id": "p",
                        "product_root": "Product",
                        "state_root": "Product-workspace/mode-state"},
                root / "archive")
            active = [json.loads(line) for line in
                      (state / "findings.jsonl").read_text().splitlines() if line.strip()]
            self.assertEqual([record["finding_id"] for record in active], ["A-01", "A-02"])
            self.assertEqual(active[1]["prevention"], "schema check")
            dropped = report["dropped"][0]["dropped_records"]
            self.assertTrue(any("A-03" in name for name in dropped))
            self.assertTrue(any("A-04" in name for name in dropped))

    def test_preflight_ignores_the_live_lease_directory(self):
        """A lease says who is replacing a file right now.

        The state root holds it, so the preflight would otherwise see an
        unexpected entry, and the name starts with a dot, which its safety rule
        refuses outright: installing would fail because a mode had been mid
        write. The directory is ephemeral by construction and is skipped with
        a note instead of being archived as stray evidence.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            (state / ".leases").mkdir(parents=True)
            (state / ".leases" / "findings.jsonl.json").write_text(
                '{"target":"findings.jsonl","session":"s1","state":"held"}\n')
            report = initialize_state(
                state, {"schema_version": 1, "project_id": "p",
                        "product_root": "Product",
                        "state_root": "Product-workspace/mode-state"},
                root / "archive")
            self.assertTrue(any(note.get("reason") ==
                                "ephemeral-lease-directory-ignored"
                                for note in report["dropped"]))
            self.assertEqual(report["archive"], None)
            self.assertTrue((state / ".leases" / "findings.jsonl.json").exists())

    def test_complete_audit_observes_before_it_reads_the_queue(self):
        """D10: reading the state first is anchoring, not diligence.

        The template used to put the state read before the audit, which inverts
        what a complete review needs: form your own observations, then check the
        persisted diagnosis against them. An incremental review is the opposite
        case and keeps the order it had. The scope is declared in the response
        and in the handoff id so the ledger can be counted afterwards.
        """
        layout = {"session_root": "P", "product_root": "P",
                  "workspace_root": "P-workspace", "state_root": "P-workspace/mode-state"}
        scope = mode_lifecycle.expected_lifecycle("auditor", layout)["audit_handoff"]["audit_scope"]
        self.assertTrue(scope["complete"]["observe_before_state"])
        self.assertFalse(scope["incremental"]["observe_before_state"])
        self.assertIn("audit-complete-", scope["handoff_id"])
        self.assertIn("audit_scope", mode_lifecycle.expected_lifecycle(
            "auditor", layout)["audit_handoff"]["final_fields"])
        prefix = mode_lifecycle.persona_prefix("project-auditor")
        self.assertIn("does-not-anchor", scope["complete"]["rule"])
        self.assertIn("BEFORE reading", prefix)
        self.assertIn("instead of anchoring you", prefix)

    def test_persona_requires_verbatim_candidate_persistence(self):
        prefix = mode_lifecycle.persona_prefix("project-continuous-repair")
        self.assertIn("persist it verbatim, field-for-field", prefix)
        self.assertIn("no field added, removed, renamed, reordered, or reformatted",
                      prefix)
        self.assertIn("never an absolute path", prefix)
        self.assertIn("recording_command", prefix)
        self.assertIn("__IMPROVEMENT_CANDIDATE_RECORD__", prefix)
        self.assertIn("recover it with the recording command", prefix)

    def test_repair_verifies_with_the_product_entrypoint_and_never_stubs(self):
        """G7: la evidencia de verificación es el entrypoint real del producto.

        La venv con el stack real de rehab no estaba disponible y el modo
        verificó con un arnés de stubs: el contrato ahora lo prohíbe como
        evidencia, obliga al entrypoint propio del producto y, cuando la
        capacidad falta, exige BLOCKED nombrando el paso de provisión.
        """
        layout = {"session_root": "parent", "product_root": "Syncify",
                  "workspace_root": "Syncify-workspace",
                  "state_root": "Syncify-workspace/mode-state"}
        contract = mode_lifecycle.expected_lifecycle("continuous-repair", layout)
        real = contract["real_stack_verification"]
        self.assertEqual(real["plan"], ".dsh-managed/capability-plan.json")
        self.assertEqual(real["evidence"], "product-own-entrypoint-only")
        self.assertEqual(real["stubs"],
                         "investigation-material-never-verification-evidence")
        self.assertEqual(real["missing_capability"],
                         "materialize-per-plan-else-BLOCKED-naming-the-step")
        self.assertEqual(
            mode_lifecycle.expected_lifecycle("auditor", layout)["real_stack_verification"],
            real)
        prefix = mode_lifecycle.persona_prefix("project-continuous-repair")
        self.assertIn("capability plan (.dsh-managed/capability-plan.json", prefix)
        self.assertIn("must never be recorded as a verification result", prefix)
        self.assertIn("BLOCKED naming the exact capability", prefix)
        self.assertIn("never substitute a stub", prefix)

    def test_repair_can_re_anchor_a_declared_base_behind_a_clean_head(self):
        """Regresión RehabWeb §6.9: base declarada ancestro del HEAD, producto limpio.

        El comando de provisión exige que el HEAD del producto coincida con
        full_base; sin ruta de re-anclaje, integrar una candidata dejaba
        bloqueado todo ciclo de reparación posterior sobre los mismos
        hallazgos (cuatro turnos RETAINED seguidos en RehabWeb).

        La ascendencia la comprueba el propio comando, no la persona: una shell
        no puede creer una prueba, así que `merge-base --is-ancestor` corre
        contra la base declarada que el modo sustituye. Una base declarada que
        no es ancestro —historia divergente, reescrita o forzada— retiene el
        turno sin llegar a mirar la candidata.
        """
        prefix = mode_lifecycle.persona_prefix("project-continuous-repair")
        self.assertIn("re-anchor-when-declared-base-is-ancestor-of-clean-head",
                      prefix)
        self.assertIn("the recorded candidate base_revision is the effective base",
                      prefix)
        self.assertIn("Findings and handoffs keep their declared base unchanged",
                      prefix)
        self.assertIn("digest16, full_base and declared_base", prefix)
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "1e1e1e1e1e1e1e1e"
            (product / "second.txt").write_text("avance\n")
            subprocess.run(["git", "-C", str(product), "add", "second.txt"],
                           check=True)
            subprocess.run([
                "git", "-C", str(product), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "avance",
            ], check=True)
            head = subprocess.check_output(
                ["git", "-C", str(product), "rev-parse", "HEAD"], text=True).strip()
            self.assertNotEqual(base, head)
            # Base declarada ancestro del HEAD: el re-anclaje es legal.
            self.assertEqual(self._run_provision(
                session, layout, head, digest, declared=base).returncode, 0)

    def test_provision_refuses_a_declared_base_that_is_not_an_ancestor(self):
        """Historial divergente: la ascendencia se comprueba, no se afirma."""
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "2e2e2e2e2e2e2e2e"
            (product / "second.txt").write_text("avance\n")
            subprocess.run(["git", "-C", str(product), "add", "second.txt"],
                           check=True)
            subprocess.run([
                "git", "-C", str(product), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "avance",
            ], check=True)
            head = subprocess.check_output(
                ["git", "-C", str(product), "rev-parse", "HEAD"], text=True).strip()
            # Una revisión que existe en el objeto store pero no en esta historia:
            # exactamente lo que deja una historia reescrita o forzada.
            orphan = subprocess.check_output(
                ["git", "-C", str(product), "commit-tree",
                 "4b825dc642cb6eb9a060e54bf8d69288fbee4904"],
                input="divergido\n", text=True).strip()
            self.assertNotEqual(
                self._run_provision(session, layout, head, digest,
                                    declared=orphan).returncode, 0)
            self.assertFalse(self._candidate(session, digest).exists())
            # La misma revisión declarada sí aprovisiona cuando es ancestro.
            self.assertEqual(
                self._run_provision(session, layout, head, digest,
                                    declared=base).returncode, 0)

    def test_provision_refuses_a_declared_base_that_is_not_a_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "3e3e3e3e3e3e3e3e"
            for bogus in ("", "HEAD", "; rm -rf /", "abc"):
                with self.subTest(declared=bogus):
                    result = self._run_provision(
                        session, layout, base, digest, declared=bogus)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self._candidate(session, digest).exists())

    def test_provision_survives_a_product_path_containing_spaces(self):
        """Un producto con espacios en la ruta parte `git -C $product` sin comillas."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "session root"
            product = session / "my product"
            workspace = session / "product workspace"
            for path in (session, product, workspace):
                path.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(product)], check=True)
            (product / "tracked.txt").write_text("uno\n")
            subprocess.run(["git", "-C", str(product), "add", "tracked.txt"],
                           check=True)
            subprocess.run([
                "git", "-C", str(product), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "base",
            ], check=True)
            base = subprocess.check_output(
                ["git", "-C", str(product), "rev-parse", "HEAD"], text=True).strip()
            layout = {"session_root": session.name, "product_root": product.name,
                      "workspace_root": workspace.name,
                      "state_root": f"{workspace.name}/mode-state"}
            digest = "4e4e4e4e4e4e4e4e"
            result = self._run_provision(session, layout, base, digest)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((session / f"my product-repair-{digest}").is_dir())

    def _run_reconcile(self, session, layout, base, finding_ids):
        command = repair_reconcile_command(layout).replace(
            "<full-base>", base).replace("<finding-ids-lf-separated>", finding_ids)
        return subprocess.run(command, cwd=session, shell=True,
                              capture_output=True, text=True)

    def test_stale_recorded_digest_recovers_without_operator_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            finding_ids = "A-01"
            digest = hashlib.sha256(
                (base + "\n" + finding_ids).encode()).hexdigest()[:16]
            self.assertEqual(self._run_provision(
                session, layout, base, digest).returncode, 0)
            candidate = session / self._candidate_name(digest)
            tracked = candidate / "tracked.txt"

            tracked.write_bytes(b"first pass bytes\n")
            first_digest, _ = self._capture_diff(session, layout, base, digest)
            tracked.write_bytes(b"second pass bytes after recording\n")
            before = tracked.read_bytes()

            stale_resume = self._run_resume(session, layout, base, digest, first_digest)
            self.assertNotEqual(stale_resume.returncode, 0)

            reconciled = self._run_reconcile(session, layout, base, finding_ids)
            self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
            marker, _, payload = reconciled.stdout.strip().partition(" ")
            self.assertEqual(marker, "__IMPROVEMENT_CANDIDATE_RECONCILE__")
            record = json.loads(payload)
            self.assertEqual(record["status"], "DIRTY")
            self.assertEqual(record["path"], self._candidate_name(digest))
            self.assertEqual(record["branch"], f"dsh/repair-{digest}")
            self.assertEqual(record["head"], base)
            self.assertEqual(record["base_revision"], base)
            self.assertEqual(record["finding_ids_digest"], hashlib.sha256(
                (base + "\n" + finding_ids).encode()).hexdigest())
            self.assertEqual(record["changed_paths"], ["tracked.txt"])
            current_digest = record["candidate_diff_digest"]

            resumed = self._run_resume(session, layout, base, digest, current_digest)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(tracked.read_bytes(), before)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(product), "status", "--porcelain=v1"], text=True), "")

    def test_stale_digest_recovery_still_requires_exact_recorded_identity(self):
        for mutation in ("wrong-findings", "other-findings", "stale-base"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                session, product, layout, base = self._provision_fixture(Path(tmp))
                finding_ids = "A-01"
                digest = hashlib.sha256(
                    (base + "\n" + finding_ids).encode()).hexdigest()[:16]
                self.assertEqual(self._run_provision(
                    session, layout, base, digest).returncode, 0)
                candidate = session / self._candidate_name(digest)
                tracked = candidate / "tracked.txt"
                tracked.write_bytes(b"stale bytes\n")
                other = session / self._candidate_name("0" * 16)
                subprocess.run([
                    "git", "-C", str(product), "worktree", "add", "-b",
                    f"dsh/repair-{'0' * 16}", str(other), base,
                ], check=True, capture_output=True)
                (other / "tracked.txt").write_bytes(b"other candidate bytes\n")
                if mutation == "wrong-findings":
                    result = self._run_reconcile(session, layout, base, "A-99")
                elif mutation == "other-findings":
                    result = self._run_reconcile(session, layout, base, "B-01")
                else:
                    result = self._run_reconcile(session, layout, "0" * 40, finding_ids)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tracked.read_bytes(), b"stale bytes\n")
                self.assertEqual((other / "tracked.txt").read_bytes(),
                                 b"other candidate bytes\n")
                self.assertEqual(subprocess.check_output(
                    ["git", "-C", str(product), "status", "--porcelain=v1"],
                    text=True), "")

    def test_provisioned_candidate_record_needs_no_diff_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "7c7c7c7c7c7c7c7c"
            self.assertEqual(self._run_provision(
                session, layout, base, digest).returncode, 0)
            candidate = session / self._candidate_name(digest)
            state = session / f"{PRODUCT}-workspace/mode-state"
            state.mkdir()
            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1, "items": [],
                "candidate": {"base_revision": base,
                              "finding_ids_digest": digest + "0" * 48,
                              "path": candidate.name,
                              "branch": f"dsh/repair-{digest}",
                              "head": base, "status": "PROVISIONED"},
            }) + "\n")
            schema = mode_lifecycle.state_schema()
            value = json.loads((state / "work-items.json").read_text())
            mode_lifecycle._valid(
                value["candidate"], schema["files"]["work-items.json"]["candidate"],
                "work-items.json.candidate")

            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1, "items": [],
                "candidate": {"base_revision": base,
                              "finding_ids_digest": digest + "0" * 48,
                              "path": candidate.name,
                              "branch": f"dsh/repair-{digest}",
                              "head": base, "status": "DIRTY"},
            }) + "\n")
            with self.assertRaises(ValueError):
                mode_lifecycle._valid(
                    json.loads((state / "work-items.json").read_text())["candidate"],
                    schema["files"]["work-items.json"]["candidate"],
                    "work-items.json.candidate")

    def test_declared_base_proof_rejects_a_divergent_base(self):
        """IMP-AUD-003: the declared base must reach the effective one, proven.

        The proof runs inside the provisioning command, against the declared
        base the mode substitutes: a shell cannot believe a claim of ancestry.
        An orphan revision and a divergent history are each refused, and the
        refusal happens before any candidate exists.
        """
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            orphan = subprocess.check_output(
                ["git", "-C", str(product), "commit-tree",
                 "4b825dc642cb6eb9a060e54bf8d69288fbee4904"],
                input="orphan\n", text=True).strip()
            digest = "0123456789abcdef"
            self.assertEqual(
                self._run_provision(session, layout, base, digest).returncode, 0)
            self.assertNotEqual(
                self._run_provision(session, layout, base, digest,
                                    declared=orphan).returncode, 0)
            self.assertFalse(self._candidate(session, "5e5e5e5e5e5e5e5e").exists())

    def test_declared_base_proof_accepts_an_ancestor_behind_a_clean_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            (product / "second.txt").write_text("avance\n")
            subprocess.run(["git", "-C", str(product), "add", "second.txt"], check=True)
            subprocess.run([
                "git", "-C", str(product), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "avance",
            ], check=True)
            head = subprocess.check_output(
                ["git", "-C", str(product), "rev-parse", "HEAD"], text=True).strip()
            self.assertNotEqual(base, head)
            digest = "6e6e6e6e6e6e6e6e"
            self.assertEqual(
                self._run_provision(session, layout, head, digest,
                                    declared=base).returncode, 0)
            # A dirty canonical product is refused: the proof is not only ancestry.
            (product / "tracked.txt").write_text("sucio\n")
            self.assertNotEqual(
                self._run_provision(session, layout, head, digest,
                                    declared=base).returncode, 0)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(product), "status", "--porcelain=v1"],
                text=True).strip(), "M tracked.txt")

    def test_provision_command_takes_exactly_the_declared_substitutions(self):
        """A placeholder the contract does not substitute is a retained turn.

        The person substitutes digest16, full_base and declared_base, so any
        other `<...>` left in the provisioning command reaches the shell
        verbatim and is read as a redirection. The declared base travels inside
        this command on purpose: the ancestry relation is proved where it is
        enforced, and nowhere else may claim it.
        """
        layout = {"session_root": "common-parent", "product_root": PRODUCT,
                  "workspace_root": f"{PRODUCT}-workspace",
                  "state_root": f"{PRODUCT}-workspace/mode-state"}
        contract = mode_lifecycle.expected_lifecycle(
            "continuous-repair", layout)["repair_candidate"]
        command = repair_provision_command(layout)
        self.assertIn("<declared-base>", command)
        self.assertEqual(sorted(_placeholders(command)),
                         ["<declared-base>", "<digest16>", "<full-base>"])
        for other in ("recording_command", "candidate_diff_command",
                      "reconcile_command", "resume_command"):
            self.assertNotIn("<declared-base>", contract[other], other)
        prefix = mode_lifecycle.persona_prefix("project-continuous-repair")
        self.assertIn("digest16, full_base and declared_base", prefix)

    def test_the_memory_the_contract_promises_is_the_memory_the_tool_consults(self):
        """A promised behaviour with no mechanical counterpart is a lie in a doc.

        E2 shipped a ledger, an index and seventeen regressions proving the
        ledger works — and nothing read the index, so the whole promise of the
        unit ("the auditor consults it before persisting a finding") was true of
        a sentence in `usage.md` and of a docstring, and false of the product.
        Every test that passed on that day was true; none of them was about the
        thing the unit was for.

        So the contract is pinned against the plugin source: each field the mode
        is told the tool computes has to be computed there, and the memory the
        persona tells the auditor to read has to be named in the contract. Drop
        either side and this fails, which is the only warning the gap had.
        """
        contract = mode_lifecycle.expected_lifecycle(
            "auditor", {"session_root": "tmpXXXXXXXXXX", "product_root": "project",
                        "workspace_root": "project-workspace",
                        "state_root": "project-workspace/mode-state"})
        anchor = contract["audit_handoff"]["evidence_anchor"]
        memory = contract["audit_handoff"]["episodic_memory"]
        self.assertEqual(anchor["fields_written_by_the_mode"], ["path", "excerpt"])
        for field in ("line", "located", "fingerprint", "prior_episode"):
            self.assertIn(field, anchor["fields_computed_by_the_tool"], field)
        self.assertIs(memory["consult_before_persisting"], True)
        self.assertEqual(memory["index"], "mode-state/episodes-index.json")
        # The persona has to ask for the consultation, or the contract asks for
        # a behaviour nobody performs.
        self.assertIn("episodes-index.json",
                      mode_lifecycle.persona_prefix("project-auditor", "auditor"))
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/dsh-plugins/workflow-write.mjs").read_text(encoding="utf-8")
        self.assertIn("readEpisodeIndex", source)
        for field in ("line", "located", "fingerprint", "prior_episode"):
            self.assertIn(field, source, field)

    def test_emitted_repair_contract_fits_the_support_file_budget(self):
        """The contract is emitted into mode.json, a budgeted support file.

        Every byte added to the lifecycle block lands in every generated mode.json,
        and the graph and context_budget layers refuse one over 25600 bytes. A
        contract that overflows the budget does not merely grow: the Host rejects
        the package it is part of, so the margin is measured here instead of being
        discovered in an acceptance run.
        """
        mode = {
            "schema_version": 1, "kind": "mode",
            "name": "project-continuous-repair",
            "preset_id": "project-continuous-repair",
            "role": "continuous-repair", "purpose": "role",
            "reuse_source": "composition", "triggers": ["role"],
            "anti_triggers": [], "inputs": [], "reads": ["project"],
            "writes": ["project-workspace/mode-state"],
            "required_capabilities": [], "forbidden_capabilities": [],
            "invariants": ["shared state"], "anti_goals": [],
            "state_machine": {"states": ["READY"], "transitions": [],
                              "initial": "READY", "terminal": ["READY"]},
            "handoffs": [],
            "failure_modes": {"retries": 0, "timeout_seconds": 60,
                              "on_failure": "retain"},
            "scenarios": ["PUBLIC-1"], "provenance": {"license": "MIT"},
        }
        layout = {"session_root": "tmpXXXXXXXXXX", "product_root": "project",
                  "workspace_root": "project-workspace",
                  "state_root": "project-workspace/mode-state"}
        for role in ("auditor", "continuous-repair"):
            document = dict(
                mode, mode_lifecycle=mode_lifecycle.expected_lifecycle(role, layout))
            size = len((json.dumps(document, indent=2) + "\n").encode())
            self.assertLessEqual(size, SUPPORT_FILE_MAX_BYTES, role)

    def test_provision_command_runs_with_a_product_root_containing_a_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            self.assertEqual(layout["product_root"], "My Product")
            result = self._run_provision(session, layout, base)
            self.assertEqual(result.returncode, 0, result.stderr)
            candidate = self._candidate(session, "0123456789abcdef")
            self.assertTrue(candidate.is_dir())
            self.assertEqual(candidate.resolve(), session.resolve() / candidate.name)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                text=True).strip(), base)

    def test_repair_provision_command_creates_registered_sibling_and_keeps_canonical_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            result = self._run_provision(session, layout, base)
            self.assertEqual(result.returncode, 0, result.stderr)
            candidate = session / self._candidate_name("0123456789abcdef")
            self.assertTrue(candidate.is_dir())
            self.assertFalse((product / candidate.name).exists())
            self.assertEqual(candidate.resolve(), session.resolve() / candidate.name)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                text=True).strip(), base)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(candidate), "branch", "--show-current"],
                text=True).strip(), "dsh/repair-0123456789abcdef")
            worktrees = subprocess.check_output(
                ["git", "-C", str(product), "worktree", "list", "--porcelain"],
                text=True)
            self.assertIn(f"worktree {candidate.resolve()}\n", worktrees)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(product), "status", "--porcelain=v1"],
                text=True), "")

    def test_repair_provision_command_reuses_only_exact_clean_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "1122334455667788"
            first = self._run_provision(session, layout, base, digest)
            self.assertEqual(first.returncode, 0, first.stderr)
            candidate = session / self._candidate_name(digest)
            inode = candidate.stat().st_ino
            second = self._run_provision(session, layout, base, digest)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(candidate.stat().st_ino, inode)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(candidate), "status", "--porcelain=v1"],
                text=True), "")

    def test_repair_dirty_candidate_resumes_on_second_turn_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            digest = "aabbccddeeff0011"
            self.assertEqual(self._run_provision(
                session, layout, base, digest).returncode, 0)
            candidate = session / self._candidate_name(digest)
            changed = candidate / "tracked.txt"
            changed.write_bytes(b"candidate repair bytes\n")
            diff_digest, paths = self._capture_diff(session, layout, base, digest)
            self.assertEqual(paths, ["tracked.txt"])
            record = {
                "base_revision": base,
                "finding_ids_digest": digest + "0" * 48,
                "path": candidate.name,
                "branch": f"dsh/repair-{digest}",
                "head": base,
                "status": "DIRTY",
                "candidate_diff_digest": diff_digest,
                "changed_paths": paths,
            }
            state = session / f"{PRODUCT}-workspace/mode-state"
            state.mkdir()
            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1, "candidate": record, "items": [],
            }) + "\n")
            before = changed.read_bytes()

            resumed = self._run_resume(
                session, layout, base, digest, record["candidate_diff_digest"])
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn("__IMPROVEMENT_DIRTY_RESUME_OK__", resumed.stdout)
            self.assertEqual(changed.read_bytes(), before)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(product), "status", "--porcelain=v1"],
                text=True), "")

    def test_repair_dirty_resume_rejects_unrecorded_or_mismatched_identity(self):
        mutations = ("unrecorded", "digest", "path", "base", "status")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                session, product, layout, base = self._provision_fixture(Path(tmp))
                digest = "1020304050607080"
                self.assertEqual(self._run_provision(
                    session, layout, base, digest).returncode, 0)
                candidate = session / self._candidate_name(digest)
                (candidate / "tracked.txt").write_bytes(b"dirty target\n")
                diff_digest, paths = self._capture_diff(session, layout, base, digest)
                record = {
                    "base_revision": base,
                    "finding_ids_digest": digest + "0" * 48,
                    "path": candidate.name,
                    "branch": f"dsh/repair-{digest}",
                    "head": base,
                    "status": "DIRTY",
                    "candidate_diff_digest": diff_digest,
                    "changed_paths": paths,
                }
                if mutation == "unrecorded":
                    record = None
                elif mutation == "digest":
                    record["candidate_diff_digest"] = "0" * 64
                elif mutation == "path":
                    record["path"] = "Product-repair-ffffffffffffffff"
                elif mutation == "base":
                    record["base_revision"] = "0" * 40
                else:
                    record["status"] = "PATCH_READY"
                exact_record = (record is not None and
                    record["path"] == candidate.name and
                    record["branch"] == f"dsh/repair-{digest}" and
                    record["base_revision"] == base and
                    record["finding_ids_digest"] == digest + "0" * 48 and
                    record["status"] in ("DIRTY", "RETAINED"))
                if exact_record:
                    result = self._run_resume(
                        session, layout, base, digest,
                        record["candidate_diff_digest"])
                else:
                    result = self._run_provision(session, layout, base, digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((candidate / "tracked.txt").read_bytes(),
                                 b"dirty target\n")
                self.assertEqual(subprocess.check_output(
                    ["git", "-C", str(product), "status", "--porcelain=v1"],
                    text=True), "")

    def test_repair_dirty_resume_rejects_symlink_and_submodule_paths(self):
        for unsafe in ("symlink", "submodule"):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as tmp:
                session, product, layout, base = self._provision_fixture(Path(tmp))
                digest = "9080706050403020"
                self.assertEqual(self._run_provision(
                    session, layout, base, digest).returncode, 0)
                candidate = session / self._candidate_name(digest)
                if unsafe == "symlink":
                    (candidate / "unsafe").symlink_to("tracked.txt")
                else:
                    nested = candidate / "nested"
                    subprocess.run(["git", "init", "-q", str(nested)], check=True)
                    (nested / "file.txt").write_text("nested\n")
                    subprocess.run(["git", "-C", str(nested), "add", "file.txt"],
                                   check=True)
                    subprocess.run([
                        "git", "-C", str(nested), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "nested",
                    ], check=True)
                    subprocess.run(["git", "-C", str(candidate), "add", "nested"],
                                   check=True, capture_output=True)
                result = self._run_command(
                    repair_candidate_diff_command, session, layout, base, digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(subprocess.check_output(
                    ["git", "-C", str(product), "status", "--porcelain=v1"],
                    text=True), "")

    def test_repair_provision_ignores_and_preserves_unrelated_worktrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, product, layout, base = self._provision_fixture(Path(tmp))
            unrelated = {}
            for kind in ("clean", "dirty", "stale"):
                path = session / f"{PRODUCT}-repair-unrelated-{kind}"
                branch = f"dsh/repair-unrelated-{kind}"
                subprocess.run([
                    "git", "-C", str(product), "worktree", "add", "-b", branch,
                    str(path), base,
                ], check=True, capture_output=True)
                unrelated[kind] = (path, branch)
            dirty_path, _ = unrelated["dirty"]
            (dirty_path / "tracked.txt").write_text("unrelated dirty bytes\n")
            stale_path, _ = unrelated["stale"]
            shutil.rmtree(stale_path)
            before_list = subprocess.check_output([
                "git", "-C", str(product), "worktree", "list", "--porcelain",
            ], text=True)
            before_refs = {
                branch: subprocess.check_output([
                    "git", "-C", str(product), "rev-parse", branch,
                ], text=True).strip()
                for _, branch in unrelated.values()
            }

            result = self._run_provision(session, layout, base, "dfd0123456789abc")
            self.assertEqual(result.returncode, 0, result.stderr)
            target = session / self._candidate_name("dfd0123456789abc")
            self.assertTrue(target.is_dir())
            after_list = subprocess.check_output([
                "git", "-C", str(product), "worktree", "list", "--porcelain",
            ], text=True)
            for path, branch in unrelated.values():
                self.assertIn(f"worktree {path.resolve()}\n", before_list)
                self.assertIn(f"worktree {path.resolve()}\n", after_list)
                self.assertIn(f"branch refs/heads/{branch}\n", after_list)
                self.assertEqual(subprocess.check_output([
                    "git", "-C", str(product), "rev-parse", branch,
                ], text=True).strip(), before_refs[branch])
            self.assertEqual((dirty_path / "tracked.txt").read_text(),
                             "unrelated dirty bytes\n")
            self.assertFalse(stale_path.exists())
            self.assertIn(f"worktree {target.resolve()}\n", after_list)

    def test_repair_provision_command_rejects_path_and_branch_collisions(self):
        for collision in ("path", "branch"):
            with self.subTest(collision=collision), tempfile.TemporaryDirectory() as tmp:
                session, product, layout, base = self._provision_fixture(Path(tmp))
                digest = "fedcba9876543210"
                candidate = session / self._candidate_name(digest)
                if collision == "path":
                    candidate.mkdir()
                else:
                    subprocess.run([
                        "git", "-C", str(product), "branch",
                        f"dsh/repair-{digest}", base,
                    ], check=True)
                result = self._run_provision(session, layout, base, digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((product / candidate.name).exists())
                self.assertEqual(subprocess.check_output(
                    ["git", "-C", str(product), "status", "--porcelain=v1"],
                    text=True), "")

    def test_integrated_candidate_survives_state_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            candidate = {
                "base_revision": "a" * 40,
                "finding_ids_digest": "b" * 64,
                "path": "Syncify-repair-bbbbbbbbbbbbbbbb",
                "branch": "dsh/repair-bbbbbbbbbbbbbbbb",
                "head": "c" * 40,
                "status": "INTEGRATED",
            }
            (state / "work-items.json").write_text(json.dumps({
                "schema_version": 1, "candidate": candidate, "items": [],
            }) + "\n")
            descriptor = {"schema_version": 1, "project_id": "syncify",
                          "product_root": "Syncify",
                          "state_root": "Syncify-workspace/mode-state"}
            initialize_state(state, descriptor, root / "archive")
            current = json.loads((state / "work-items.json").read_text())
            self.assertEqual(current["candidate"], candidate)
            self.assertFalse((root / "archive").exists())

    def test_compaction_deduplicates_by_finding_and_base_keeping_newest(self):
        records = [
            {"finding_id": "A-01", "base_revision": "one", "value": 1},
            {"finding_id": "M-02", "base_revision": "one", "value": 2},
            {"finding_id": "A-01", "base_revision": "one", "value": 3},
            {"finding_id": "A-01", "base_revision": "two", "value": 4},
        ]
        self.assertEqual(compact_records(
            records, ("finding_id", "base_revision"), 2), [records[2], records[3]])

    def test_compaction_rejects_missing_dedupe_identity(self):
        with self.assertRaisesRegex(ValueError, "missing dedupe field"):
            compact_records([{"finding_id": "A-01"}],
                            ("finding_id", "base_revision"), 200)

    def test_initialize_state_creates_versioned_bounded_schema_and_candidate_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            initialize_state(state, descriptor)
            schema = json.loads((state / "state-schema.json").read_text())
            self.assertEqual(schema["schema_version"], 1)
            self.assertEqual(schema["files"]["findings.jsonl"]["limit"],
                             LIMITS["findings.jsonl"])
            self.assertEqual(json.loads((state / "work-items.json").read_text()), {
                "schema_version": 1, "candidate": None, "items": [],
            })
            for name in ("findings.jsonl", "handoffs.jsonl",
                         "verification-results.jsonl", "overflows.jsonl"):
                self.assertEqual((state / name).read_text(), "")

    def test_initialize_state_migrates_legacy_empty_work_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            (state / "work-items.json").write_text("[]\n")
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            archive = Path(tmp) / "archive"
            initialize_state(state, descriptor, archive)
            self.assertIsNone(json.loads(
                (state / "work-items.json").read_text())["candidate"])
            generation, = archive.iterdir()
            self.assertEqual((generation / "files" /
                              "active-work-items.json").read_bytes(), b"[]\n")

    def test_initialize_state_migrates_legacy_schema_after_full_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            initialize_state(state, descriptor)
            schema_path = state / "state-schema.json"
            schema = json.loads(schema_path.read_text())
            for spec in schema["files"].values():
                spec.pop("max_bytes", None)
                spec.pop("record", None)
                spec.pop("item", None)
                spec.pop("candidate", None)
            schema.pop("record_max_bytes")
            schema["files"]["verification-results.jsonl"]["dedupe_key"] = [
                "finding_id", "candidate_commit"]
            schema_path.write_text(json.dumps(schema))
            report = initialize_state(state, descriptor, root / "archive")
            migrated = json.loads(schema_path.read_text())
            self.assertIn("record_max_bytes", migrated)
            self.assertIn("overflows.jsonl", migrated["files"])
            self.assertEqual(report["dropped"], [
                {"file": "state-schema.json",
                 "reason": "incompatible-expected-file"}])
            self.assertIsNotNone(report["archive"])

    def test_initialize_state_archives_malformed_expected_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            bad = state / "findings.jsonl"
            bad.write_text("not-json\n")
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            initialize_state(state, descriptor, root / "archive")
            self.assertEqual(bad.read_bytes(), b"")
            generation, = (root / "archive").iterdir()
            self.assertEqual((generation / "files" /
                              "active-findings.jsonl").read_bytes(), b"not-json\n")

    def test_initialize_state_rejects_oversized_and_unsafe_files(self):
        descriptor = {"schema_version": 1, "project_id": "project",
                      "product_root": "Project",
                      "state_root": "Project-workspace/mode-state"}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            (state / "findings.jsonl").write_bytes(
                b"x" * (BYTE_LIMITS["findings.jsonl"] + 1))
            archive = Path(tmp) / "archive"
            initialize_state(state, descriptor, archive)
            self.assertEqual((state / "findings.jsonl").read_bytes(), b"")
            generation, = archive.iterdir()
            self.assertEqual((generation / "files" /
                              "active-findings.jsonl").stat().st_size,
                             BYTE_LIMITS["findings.jsonl"] + 1)
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            target = Path(tmp) / "target"
            target.write_text("")
            (state / "findings.jsonl").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                initialize_state(state, descriptor)

    def test_initialize_state_rejects_unbounded_legacy_before_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            legacy = [{"work_item_id": f"W-{i}", "finding_id": "A-01",
                       "base_revision": "a" * 40, "status": "PENDING"}
                      for i in range(LIMITS["work-items.json"] + 1)]
            path = state / "work-items.json"
            path.write_text(json.dumps(legacy))
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            archive = Path(tmp) / "archive"
            original = path.read_bytes()
            initialize_state(state, descriptor, archive)
            migrated = json.loads(path.read_text())
            self.assertEqual(len(migrated["items"]), LIMITS["work-items.json"])
            self.assertEqual(migrated["items"][0]["work_item_id"], "W-1")
            generation, = archive.iterdir()
            self.assertEqual((generation / "files" /
                              "active-work-items.json").read_bytes(), original)

    def test_initialize_state_receipts_records_dropped_only_by_the_limit(self):
        """The record cap drops valid records, so it owes the same receipt.

        The limit is not a compatibility signal: 250 well formed findings
        compact to 200 with incompatible=False and dropped=[], so the
        compacted file replaced the original and 50 findings left the live
        state with no receipt in overflows.jsonl and no archived copy. The
        repair of one of them then landed in the product with no record left
        to stand on. SYNC-AUD-047 was lost exactly that way.
        """
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            revision = "a" * 40
            records = [{"finding_id": f"IMP-AUD-{index:04d}", "base_revision": revision,
                        "severity": "HIGH", "summary": f"finding {index}", "status": "OPEN"}
                       for index in range(LIMITS["findings.jsonl"] + 50)]
            path = state / "findings.jsonl"
            original = "".join(json.dumps(record) + "\n" for record in records).encode()
            path.write_bytes(original)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            archive = Path(tmp) / "archive"
            report = initialize_state(state, descriptor, archive)
            kept = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(kept), LIMITS["findings.jsonl"])
            self.assertEqual(kept[0]["finding_id"], records[50]["finding_id"])
            note, = [item for item in report["dropped"] if item["file"] == "findings.jsonl"]
            # The receipt caps at 32 identities by contract; the archived copy
            # is what keeps the remaining 18 reachable.
            self.assertEqual(note["dropped_records"],
                             [f"findings.jsonl#{record['finding_id']}"
                              for record in records[:32]])
            generation, = archive.iterdir()
            self.assertEqual((generation / "files" / "active-findings.jsonl").read_bytes(),
                             original)

    def test_initialize_state_receipts_work_items_dropped_only_by_the_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            items = [{"work_item_id": f"W-{index:04d}", "finding_id": f"IMP-AUD-{index:04d}",
                      "base_revision": "a" * 40, "status": "PENDING"}
                     for index in range(LIMITS["work-items.json"] + 10)]
            path = state / "work-items.json"
            original = json.dumps({"schema_version": 1, "candidate": None,
                                   "items": items}).encode()
            path.write_bytes(original)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            archive = Path(tmp) / "archive"
            report = initialize_state(state, descriptor, archive)
            migrated = json.loads(path.read_text())
            self.assertEqual(len(migrated["items"]), LIMITS["work-items.json"])
            self.assertEqual(migrated["items"][0]["work_item_id"], "W-0010")
            note, = [entry for entry in report["dropped"]
                     if entry["file"] == "work-items.json"]
            self.assertEqual(note["dropped_records"],
                             [f"W-{index:04d}" for index in range(10)])
            generation, = archive.iterdir()
            self.assertEqual((generation / "files" / "active-work-items.json").read_bytes(),
                             original)

    def test_finding_summary_longer_than_one_kibibyte_survives_the_preflight(self):
        """A real audit summary is evidence-dense and routinely passes 1 KiB.

        The schema used to cap every text field at 1024 characters while a whole
        record may be 4096 bytes, so the preflight rejected those findings,
        rebuilt findings.jsonl without them and reported nothing: the repair
        could still land in the product while the record never came back. SYNC-AUD-047
        was lost that way and only an audit found it months later.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            revision = "a" * 40
            # The real case: 1245 characters, 1561 bytes on the wire.
            long_summary = "x" * 1245
            self.assertGreater(len(long_summary), 1024)
            findings = [
                {"finding_id": "SYNC-AUD-047", "base_revision": revision,
                 "severity": "HIGH", "summary": long_summary, "status": "OPEN"},
            ]
            (state / "findings.jsonl").write_bytes(
                b"".join(json.dumps(item).encode() + b"\n" for item in findings))
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            initialize_state(state, descriptor, root / "archive")

            active = [json.loads(line) for line in
                      (state / "findings.jsonl").read_text().splitlines()]
            self.assertEqual([item["finding_id"] for item in active],
                             ["SYNC-AUD-047"])
            self.assertEqual(active[0]["summary"], long_summary)
            # Nothing was dropped, so nothing needed archiving.
            self.assertFalse((root / "archive").exists())

    def test_text_fields_are_bounded_by_the_record_cap_not_a_literal(self):
        """Pin the bound structurally so it cannot be re-tightened below the cap."""
        schema = state_schema()
        findings = schema["files"]["findings.jsonl"]["record"]
        for field in ("finding_id", "summary"):
            self.assertEqual(findings["properties"][field]["maxLength"],
                             RECORD_BYTE_LIMIT)
        handoffs = schema["files"]["handoffs.jsonl"]["record"]
        for field in ("handoff_id", "next_prompt"):
            self.assertEqual(handoffs["properties"][field]["maxLength"],
                             RECORD_BYTE_LIMIT)
        verification = schema["files"]["verification-results.jsonl"]["record"]
        self.assertEqual(verification["properties"]["command"]["maxLength"],
                         RECORD_BYTE_LIMIT)
        # A record that is legal under the schema still fits the byte cap.
        self.assertEqual(findings["max_bytes"], RECORD_BYTE_LIMIT)

    def test_dropped_record_identities_are_named_in_the_archive_receipt(self):
        """A record that leaves the live state must be visible in the evidence."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            revision = "a" * 40
            findings = [
                {"finding_id": "A-01", "base_revision": revision,
                 "severity": "HIGH", "summary": "current", "status": "OPEN"},
                {"finding_id": "A-02", "base_revision": revision,
                 "severity": "NOT-A-SEVERITY", "summary": "broken enum", "status": "OPEN"},
            ]
            finding_bytes = b"".join(json.dumps(item).encode() + b"\n" for item in findings)
            (state / "findings.jsonl").write_bytes(finding_bytes)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            initialize_state(state, descriptor, root / "archive")

            active = [json.loads(line) for line in
                      (state / "findings.jsonl").read_text().splitlines()]
            self.assertEqual([item["finding_id"] for item in active], ["A-01"])
            generation, = (root / "archive").iterdir()
            receipt = json.loads((generation / "receipt.json").read_text())
            by_source = {item["source_path"]: item for item in receipt["files"]}
            self.assertEqual(by_source["findings.jsonl"]["dropped_records"],
                             ["findings.jsonl#A-02"])
            # The original bytes are still recoverable.
            self.assertEqual(
                (generation / "files" / "active-findings.jsonl").read_bytes(),
                finding_bytes)

    def test_mixed_records_preserve_whole_original_and_migrate_only_safe_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            revision = "a" * 40
            findings = [
                {"finding_id": "A-01", "base_revision": revision,
                 "severity": "HIGH", "summary": "current", "status": "OPEN"},
                {"id": "A-02", "base_revision": revision,
                 "severity": "MEDIUM", "summary": "legacy", "status": "OPEN"},
                {"summary": "candidate summary without identity"},
            ]
            verification = [
                {"finding_id": "A-01", "candidate_head": revision,
                 "candidate_diff_digest": "b" * 64,
                 "result": "PASS", "command": "pytest"},
                {"finding_id": "A-02", "candidate_commit": revision,
                 "red": {"command": "pytest", "result": "FAIL"},
                 "green": {"command": "pytest", "result": "PASS"}},
                {"summary": "candidate passed"},
            ]
            finding_bytes = b"".join(json.dumps(item).encode() + b"\n" for item in findings)
            verification_bytes = b"".join(json.dumps(item).encode() + b"\n" for item in verification)
            (state / "findings.jsonl").write_bytes(finding_bytes)
            (state / "verification-results.jsonl").write_bytes(verification_bytes)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            initialize_state(state, descriptor, root / "archive")

            active_findings = [json.loads(line) for line in
                               (state / "findings.jsonl").read_text().splitlines()]
            self.assertEqual([item["finding_id"] for item in active_findings],
                             ["A-01", "A-02"])
            active_verification = [json.loads(line) for line in
                                   (state / "verification-results.jsonl").read_text().splitlines()]
            self.assertEqual(active_verification, [verification[0]])
            generation, = (root / "archive").iterdir()
            self.assertEqual((generation / "files" / "active-findings.jsonl").read_bytes(),
                             finding_bytes)
            self.assertEqual((generation / "files" /
                              "active-verification-results.jsonl").read_bytes(),
                             verification_bytes)
            receipt = json.loads((generation / "receipt.json").read_text())
            by_source = {item["source_path"]: item for item in receipt["files"]}
            self.assertEqual(by_source["findings.jsonl"]["reason"],
                             "incompatible-records")
            self.assertEqual(by_source["findings.jsonl"]["sha256"],
                             hashlib.sha256(finding_bytes).hexdigest())

    def test_old_work_items_shapes_preserve_original_and_keep_only_valid_items(self):
        descriptor = {"schema_version": 1, "project_id": "project",
                      "product_root": "Project",
                      "state_root": "Project-workspace/mode-state"}
        revision = "a" * 40
        valid = {"work_item_id": "W-01", "finding_id": "A-01",
                 "base_revision": revision, "status": "PENDING"}
        for value, expected in (([valid, {"summary": "old"}], [valid]),
                                ({"items": [valid], "candidate": {"path": "old"}}, [valid])):
            with self.subTest(shape=type(value).__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = root / "mode-state"
                state.mkdir()
                original = (json.dumps(value) + "\n").encode()
                (state / "work-items.json").write_bytes(original)
                initialize_state(state, descriptor, root / "archive")
                self.assertEqual(json.loads((state / "work-items.json").read_text())["items"],
                                 expected)
                generation, = (root / "archive").iterdir()
                self.assertEqual((generation / "files" /
                                  "active-work-items.json").read_bytes(), original)

    def test_equivalent_legacy_project_descriptor_is_migrated_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            old = {**descriptor, "workspace_root": "Project-workspace"}
            original = (json.dumps(old) + "\n").encode()
            (state / "project.json").write_bytes(original)
            initialize_state(state, descriptor, root / "archive")
            self.assertEqual(json.loads((state / "project.json").read_text()), descriptor)
            generation, = (root / "archive").iterdir()
            self.assertEqual((generation / "files" /
                              "active-project.json").read_bytes(), original)

    def test_archives_legacy_evidence_with_receipt_and_idempotent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            archive_root = root / ".dsh-managed" / "mode-state-legacy"
            state.mkdir()
            evidence = {"a01-check-red.txt": b"red\x00evidence\n",
                        "candidate-repair.patch": b"diff --git a/a b/a\n"}
            for name, data in evidence.items():
                (state / name).write_bytes(data)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            initialize_state(state, descriptor, archive_root)

            generations = list(archive_root.iterdir())
            self.assertEqual(len(generations), 1)
            receipt = json.loads((generations[0] / "receipt.json").read_text())
            inventory = json.loads((generations[0] / "inventory.json").read_text())
            self.assertEqual(receipt["files"], inventory)
            self.assertEqual({item["name"] for item in inventory}, set(evidence))
            for name, data in evidence.items():
                self.assertFalse((state / name).exists())
                self.assertEqual((generations[0] / "files" / name).read_bytes(), data)

            initialize_state(state, descriptor, archive_root)
            self.assertEqual(list(archive_root.iterdir()), generations)

    def test_retry_reuses_verified_archive_after_interrupted_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            archive_root = root / "archive"
            state.mkdir()
            evidence = state / "m02-fmt-red.txt"
            evidence.write_bytes(b"format failed\n")
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            real_unlink = Path.unlink
            with unittest.mock.patch.object(
                    Path, "unlink", autospec=True,
                    side_effect=lambda path, *args, **kwargs:
                    (_ for _ in ()).throw(OSError("injected"))
                    if path == evidence else real_unlink(path, *args, **kwargs)):
                with self.assertRaisesRegex(OSError, "injected"):
                    initialize_state(state, descriptor, archive_root)
            self.assertEqual(evidence.read_bytes(), b"format failed\n")
            self.assertEqual(len(list(archive_root.iterdir())), 1)

            initialize_state(state, descriptor, archive_root)
            self.assertFalse(evidence.exists())
            self.assertEqual(len(list(archive_root.iterdir())), 1)

    def test_legacy_archive_accepts_exact_file_and_total_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            archive_root = root / "archive"
            state.mkdir()
            for index in range(LEGACY_TOTAL_BYTE_LIMIT // LEGACY_FILE_BYTE_LIMIT):
                (state / f"evidence-{index}.bin").write_bytes(
                    bytes([index]) * LEGACY_FILE_BYTE_LIMIT)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            initialize_state(state, descriptor, archive_root)

            generation, = archive_root.iterdir()
            receipt = json.loads((generation / "receipt.json").read_text())
            self.assertEqual(receipt["total_bytes"], LEGACY_TOTAL_BYTE_LIMIT)
            self.assertEqual(receipt["limits"], {
                "per_file_bytes": LEGACY_FILE_BYTE_LIMIT,
                "total_bytes": LEGACY_TOTAL_BYTE_LIMIT,
            })
            self.assertTrue(all(item["size"] == LEGACY_FILE_BYTE_LIMIT
                                for item in receipt["files"]))

    def test_legacy_archive_rejects_one_byte_over_total_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            for index in range(LEGACY_TOTAL_BYTE_LIMIT // LEGACY_FILE_BYTE_LIMIT):
                (state / f"evidence-{index}.bin").write_bytes(
                    bytes([index]) * LEGACY_FILE_BYTE_LIMIT)
            (state / "overflow.bin").write_bytes(b"x")
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}

            with self.assertRaisesRegex(ValueError, "exceeds total cap"):
                initialize_state(state, descriptor, root / "archive")
            self.assertFalse((root / "archive").exists())

    def test_legacy_preflight_rejects_symlink_hardlink_and_oversize(self):
        descriptor = {"schema_version": 1, "project_id": "project",
                      "product_root": "Project",
                      "state_root": "Project-workspace/mode-state"}
        for kind in ("symlink", "hardlink", "oversize"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = root / "mode-state"
                state.mkdir()
                legacy = state / "legacy.txt"
                target = root / "target"
                target.write_bytes(b"evidence")
                if kind == "symlink":
                    legacy.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, legacy)
                else:
                    legacy.write_bytes(b"x" * (LEGACY_FILE_BYTE_LIMIT + 1))
                with self.assertRaisesRegex(ValueError, "unsafe|oversized"):
                    initialize_state(state, descriptor, root / "archive")
                self.assertTrue(legacy.exists())
                self.assertFalse((root / "archive").exists())

    def test_expected_file_write_failure_rolls_back_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            original = b'{"summary":"legacy candidate"}\n'
            path = state / "verification-results.jsonl"
            path.write_bytes(original)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            real_replace = mode_lifecycle._replace_bytes

            def fail_state_write(target, data):
                if target.name == "project.json":
                    raise OSError("injected state write failure")
                return real_replace(target, data)

            with unittest.mock.patch("mode_lifecycle._replace_bytes",
                                     side_effect=fail_state_write):
                with self.assertRaisesRegex(OSError, "injected state write failure"):
                    initialize_state(state, descriptor, root / "archive")
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((state / "project.json").exists())

    def test_failure_after_removal_rolls_back_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "mode-state"
            state.mkdir()
            legacy = state / "pre-repair-candidate.patch"
            original = b"candidate bytes\x00\n"
            legacy.write_bytes(original)
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            real_replace = mode_lifecycle._replace_bytes

            def fail_state_write(path, data):
                if path.name == "project.json":
                    raise OSError("injected state write failure")
                return real_replace(path, data)

            with unittest.mock.patch("mode_lifecycle._replace_bytes",
                                     side_effect=fail_state_write):
                with self.assertRaisesRegex(OSError, "injected state write failure"):
                    initialize_state(state, descriptor, root / "archive")
            self.assertEqual(legacy.read_bytes(), original)
            self.assertFalse((state / "project.json").exists())


if __name__ == "__main__":
    unittest.main()
