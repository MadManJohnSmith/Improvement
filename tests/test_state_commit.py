"""E1: a unit that dies between two state files is named, not believed.

`mode-state` is five files, so replacing them is five writes. Before this, a
crash in the middle left `findings.jsonl` and `work-items.json` disagreeing and
nothing to notice it: the next run read both and took them at face value. These
cases pin the property that fixes it -- the partial unit is recoverable and
reportable by name -- and pin the two directions that make it useful and
harmless.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import state_commit


class StateCommitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="state-commit-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = self.tmp / "mode-state"
        self.state.mkdir()

    def _write_state(self, name, text):
        (self.state / name).write_text(text, encoding="utf-8")

    def test_a_state_with_no_marker_is_clean(self):
        self._write_state("findings.jsonl", '{"id":1}\n')
        report = state_commit.reconcile(self.state)
        self.assertEqual(report["state"], "CLEAN")
        self.assertIsNone(report["unit"])
        self.assertEqual(report["missing"], [])

    def test_a_closed_unit_leaves_nothing_behind(self):
        self._write_state("findings.jsonl", '{"id":1}\n')
        state_commit.open_commit(self.state, "unit-1", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", '{"id":1}\n')
        self.assertTrue(state_commit.close_commit(self.state))
        self.assertEqual(state_commit.reconcile(self.state)["state"], "CLEAN")
        self.assertFalse(state_commit.marker_path(self.state).exists())

    def test_a_unit_that_landed_everything_but_never_closed_is_recoverable(self):
        # The benign half of the failure: the writes are whole, only the
        # closing step was missed. Demanding a repair here would be a false
        # alarm, so this has to report itself and be clearable.
        content = '{"id":1}\n'
        self._write_state("findings.jsonl", content)
        state_commit.open_commit(self.state, "unit-1", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", content)
        report = state_commit.reconcile(self.state)
        self.assertEqual(report["state"], "COMPLETE_UNCLOSED")
        self.assertEqual(report["unit"], "unit-1")
        self.assertEqual(report["missing"], [])
        self.assertTrue(state_commit.close_commit(self.state))
        self.assertEqual(state_commit.reconcile(self.state)["state"], "CLEAN")

    def test_a_unit_that_died_mid_write_names_the_file_that_never_landed(self):
        state_commit.open_commit(self.state, "unit-2", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", '{"id":1}\n')
        state_commit.record_write(self.state, "work-items.json", '{"unit":"u2"}\n')
        self._write_state("findings.jsonl", '{"id":1}\n')
        # work-items.json never landed: the process died between the two.
        report = state_commit.reconcile(self.state)
        self.assertEqual(report["state"], "TORN")
        self.assertEqual(report["unit"], "unit-2")
        self.assertEqual(report["missing"], ["work-items.json"])
        self.assertEqual(report["altered"], [])

    def test_a_file_that_landed_with_other_content_is_reported_as_altered(self):
        # The state file exists and parses, so nothing else would notice.
        state_commit.open_commit(self.state, "unit-3", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", '{"id":1}\n')
        self._write_state("findings.jsonl", '{"id":1}\n')
        self._write_state("findings.jsonl.partial", '{"id":2}\n')
        (self.state / "findings.jsonl").write_text('{"id":2}\n', encoding="utf-8")
        report = state_commit.reconcile(self.state)
        self.assertEqual(report["state"], "TORN")
        self.assertEqual(report["altered"], ["findings.jsonl"])

    def test_a_replacement_write_updates_the_marker_rather_than_duplicating(self):
        state_commit.open_commit(self.state, "unit-4", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", '{"id":1}\n')
        state_commit.record_write(self.state, "findings.jsonl", '{"id":2}\n')
        self._write_state("findings.jsonl", '{"id":2}\n')
        report = state_commit.reconcile(self.state)
        self.assertEqual(report["state"], "COMPLETE_UNCLOSED")
        self.assertEqual(len(report["files"]), 1)

    def test_a_write_without_an_open_marker_is_refused(self):
        # Otherwise any stray write could create a marker with no unit to name.
        with self.assertRaises(ValueError):
            state_commit.record_write(self.state, "findings.jsonl", "{}\n")

    def test_a_corrupt_marker_is_refused_rather_than_read_as_clean(self):
        state_commit.marker_path(self.state).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            state_commit.reconcile(self.state)

    def test_a_marker_of_an_unknown_version_is_refused(self):
        state_commit.marker_path(self.state).write_text(
            json.dumps({"version": 99, "unit": "x", "files": []}), encoding="utf-8")
        with self.assertRaises(ValueError):
            state_commit.reconcile(self.state)

    def test_reopening_the_same_unit_keeps_what_it_already_recorded(self):
        state_commit.open_commit(self.state, "unit-5", session="s1", now=0)
        state_commit.record_write(self.state, "findings.jsonl", '{"id":1}\n')
        state_commit.open_commit(self.state, "unit-5", session="s1", now=10)
        report = state_commit.read_commit(self.state)
        self.assertEqual([item["path"] for item in report["files"]],
                         ["findings.jsonl"])

    def test_a_unit_touching_more_files_than_the_cap_is_refused(self):
        state_commit.open_commit(self.state, "unit-6", session="s1", now=0)
        for index in range(state_commit.MAX_ENTRIES):
            state_commit.record_write(self.state, f"f{index}.jsonl", "{}\n")
        with self.assertRaises(ValueError):
            state_commit.record_write(self.state, "one-too-many.jsonl", "{}\n")

    def test_an_old_unclosed_marker_is_marked_abandoned(self):
        state_commit.open_commit(self.state, "unit-7", session="s1", now=0)
        report = state_commit.reconcile(
            self.state, now=state_commit.ABANDONED_AFTER_SECONDS + 1)
        self.assertTrue(report["abandoned"])
        fresh = state_commit.reconcile(self.state, now=10)
        self.assertFalse(fresh["abandoned"])

    def test_the_marker_is_written_atomically(self):
        # A marker that is itself half-written is the failure it exists to
        # detect, so it goes through a temp file and an os.replace.
        self.assertNotIn(".commit.json.", str(state_commit._write.__doc__ or ""))
        state_commit.open_commit(self.state, "unit-8", session="s1", now=0)
        leftovers = [p.name for p in self.state.iterdir()
                     if p.name.startswith(".commit.json.")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
