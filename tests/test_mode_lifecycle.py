import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mode_lifecycle
from mode_lifecycle import (BYTE_LIMITS, LEGACY_FILE_BYTE_LIMIT,
                            LEGACY_TOTAL_BYTE_LIMIT, LIMITS, compact_records,
                            initialize_state, startup_check)


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
                         "verification-results.jsonl"):
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
            state = Path(tmp) / "mode-state"
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
            initialize_state(state, descriptor)
            self.assertIn("record_max_bytes", json.loads(schema_path.read_text()))

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
