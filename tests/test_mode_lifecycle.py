import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mode_lifecycle import BYTE_LIMITS, LIMITS, compact_records, initialize_state


class ModeLifecycleTests(unittest.TestCase):
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
            initialize_state(state, descriptor)
            self.assertIsNone(json.loads(
                (state / "work-items.json").read_text())["candidate"])

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

    def test_initialize_state_rejects_malformed_without_partial_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            bad = state / "findings.jsonl"
            bad.write_text("not-json\n")
            descriptor = {"schema_version": 1, "project_id": "project",
                          "product_root": "Project",
                          "state_root": "Project-workspace/mode-state"}
            with self.assertRaisesRegex(ValueError, "malformed JSON"):
                initialize_state(state, descriptor)
            self.assertEqual(bad.read_text(), "not-json\n")
            self.assertFalse((state / "project.json").exists())

    def test_initialize_state_rejects_oversized_and_unsafe_files(self):
        descriptor = {"schema_version": 1, "project_id": "project",
                      "product_root": "Project",
                      "state_root": "Project-workspace/mode-state"}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "mode-state"
            state.mkdir()
            (state / "findings.jsonl").write_bytes(
                b"x" * (BYTE_LIMITS["findings.jsonl"] + 1))
            with self.assertRaisesRegex(ValueError, "oversized"):
                initialize_state(state, descriptor)
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
            initialize_state(state, descriptor)
            migrated = json.loads(path.read_text())
            self.assertEqual(len(migrated["items"]), LIMITS["work-items.json"])
            self.assertEqual(migrated["items"][0]["work_item_id"], "W-1")


if __name__ == "__main__":
    unittest.main()
