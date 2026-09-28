import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mode_lifecycle import LIMITS, compact_records, initialize_state


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


if __name__ == "__main__":
    unittest.main()
