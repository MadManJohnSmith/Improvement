"""E2: the framework remembers what it already fixed, and refuses to remember
what it did not.

The failure this exists to prevent is repetition: an auditor that meets the same
defect every session writes a finding every session, and a repairer retries an
approach that already failed. These cases pin the two decisions that make the
memory useful rather than a second source of duplicates -- identity by
fingerprint, and an episode only for a verified repair -- plus the recall path
the auditor uses before persisting.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import episodes


class EpisodesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="episodes-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.workspace = self.tmp / "ws"
        self.workspace.mkdir()

    def _close(self, unit="unit-1", path="src/a.py", excerpt="token = 1",
               verdict="PASS", evidence="pytest: 12 passed", repair="rotar el secreto",
               fingerprint=None):
        return episodes.record(self.workspace, unit=unit, path=path,
                               excerpt=excerpt, verdict=verdict,
                               evidence=evidence, repair=repair,
                               fingerprint=fingerprint)

    def test_recall_starts_empty_and_says_so(self):
        self.assertEqual(episodes.recall(self.workspace, "src/a.py", "x"), [])

    def test_a_verified_repair_is_remembered_and_recalled(self):
        episode = self._close()
        self.assertEqual(episode["verdict"], "PASS")
        found = episodes.recall(self.workspace, "src/a.py", "token = 1")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["unit"], "unit-1")
        self.assertEqual(found[0]["repair"], "rotar el secreto")

    def test_the_same_defect_described_twice_is_one_entry(self):
        # Identity is the fingerprint, so wording cannot fork the memory into
        # two lines that both look new.
        self._close(unit="unit-1", excerpt="token = 1", fingerprint="fp-abc")
        self._close(unit="unit-2", excerpt="credential = 1  # token",
                    fingerprint="fp-abc")
        self.assertEqual(episodes.stats(self.workspace)["signatures"], 1)
        self.assertEqual(episodes.stats(self.workspace)["episodes"], 2)

    def test_a_different_defect_is_a_different_signature(self):
        self._close(unit="unit-1", path="src/a.py", excerpt="x")
        self._close(unit="unit-2", path="src/b.py", excerpt="y")
        self.assertEqual(episodes.stats(self.workspace)["signatures"], 2)

    def test_a_repeat_is_recognisable_before_persisting(self):
        """Recall is the reader; stamping the repeat is the plugin's job.

        This module is the Host side: it owns the ledger, the index and the
        query. It does not decide that a finding is a repeat — `workflow_write`
        does, by looking up the fingerprint it already computes and stamping
        `prior_episode` — because a Python helper nothing called for two units
        is how the auditor ended up repeating itself while seventeen green
        tests watched. The stamping side is proven in
        `tests/test_workflow_write_plugin.py`; this is the query it queries.
        """
        self._close()
        found = episodes.recall(self.workspace, "src/a.py", "token = 1")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["unit"], "unit-1")
        # The same code in a file the memory has never seen is not a repeat,
        # which is the property that keeps the count meaningful.
        self.assertEqual(episodes.recall(self.workspace, "src/c.py", "other"), [])

    def test_an_unverified_attempt_is_not_remembered(self):
        # Recording a fix that did not verify teaches the next session to retry
        # it, which is the exact failure the memory is meant to stop.
        for verdict in ("FAIL", "BLOCKED", "NOT_COVERED"):
            with self.subTest(verdict=verdict):
                with self.assertRaises(ValueError):
                    self._close(unit=f"unit-{verdict}", verdict=verdict)
        self.assertEqual(episodes.stats(self.workspace)["episodes"], 0)

    def test_the_signature_prefers_the_tool_fingerprint_over_wording(self):
        by_fingerprint = episodes.signature("src/a.py", "one wording", "fp-1")
        by_wording = episodes.signature("src/a.py", "one wording")
        self.assertNotEqual(by_fingerprint, by_wording)
        self.assertEqual(by_fingerprint, episodes.signature("src/b.py", "other", "fp-1"))

    def test_a_signature_needs_a_path_and_an_excerpt(self):
        with self.assertRaises(ValueError):
            episodes.signature(None, "x")
        with self.assertRaises(ValueError):
            episodes.signature("src/a.py", None)

    def test_recall_needs_something_to_look_up(self):
        with self.assertRaises(ValueError):
            episodes.recall(self.workspace)

    def test_the_ledger_is_append_only_and_readable_line_by_line(self):
        self._close(unit="unit-1", fingerprint="fp-1")
        self._close(unit="unit-2", fingerprint="fp-1")
        lines = episodes.ledger_path(self.workspace).read_text(
            encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual([json.loads(line)["unit"] for line in lines],
                         ["unit-1", "unit-2"])

    def test_a_crash_that_half_wrote_the_last_line_does_not_poison_the_ledger(self):
        # The ledger is appended in place, so a crash can leave a partial line.
        # Refusing to read it would lose every earlier episode with it.
        self._close(unit="unit-1", fingerprint="fp-1")
        self._close(unit="unit-2", fingerprint="fp-1")
        with episodes.ledger_path(self.workspace).open("a", encoding="utf-8") as stream:
            stream.write('{"version": 1, "unit": "unit-3", "sig')
        records = episodes.read_episodes(self.workspace)
        self.assertEqual([r["unit"] for r in records], ["unit-1", "unit-2"])
        self.assertEqual(episodes.stats(self.workspace)["episodes"], 2)

    def test_a_corrupt_line_in_the_middle_is_refused(self):
        # A torn last line is a crash; a broken line in the middle is a real
        # corruption and must not be read as if the episodes before it were all
        # there were fine and the rest simply does not exist.
        self._close(unit="unit-1", fingerprint="fp-1")
        self._close(unit="unit-2", fingerprint="fp-1")
        path = episodes.ledger_path(self.workspace)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        path.write_text(lines[0] + "\n" + "{broken}\n" + lines[1] + "\n",
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            episodes.read_episodes(self.workspace)

    def test_a_signature_keeps_only_the_last_few_episodes(self):
        for index in range(episodes.MAX_PER_SIGNATURE + 3):
            self._close(unit=f"unit-{index}", fingerprint="fp-loop")
        kept = episodes.recall(self.workspace, fingerprint="fp-loop", limit=0)
        self.assertEqual(len(kept), episodes.MAX_PER_SIGNATURE)
        self.assertEqual(kept[-1]["unit"],
                         f"unit-{episodes.MAX_PER_SIGNATURE + 2}")

    def test_an_empty_or_malformed_field_is_refused(self):
        with self.assertRaises(ValueError):
            self._close(unit="")
        with self.assertRaises(ValueError):
            self._close(evidence="   ")
        with self.assertRaises(ValueError):
            self._close(evidence="x" * 2000)
        with self.assertRaises(ValueError):
            self._close(verdict="PROBABLY_FINE")

    def test_a_corrupt_index_is_refused_rather_than_read_as_empty(self):
        # Reading a broken index as "nothing known" would make every known
        # defect look new, which is the failure this module exists to prevent.
        episodes.index_path(self.workspace).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            episodes.read_index(self.workspace)
        with self.assertRaises(ValueError):
            episodes.recall(self.workspace, "src/a.py", "x")

    def test_an_index_of_an_unknown_version_is_refused(self):
        episodes.index_path(self.workspace).write_text(
            json.dumps({"version": 99, "signatures": {}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            episodes.read_index(self.workspace)

    def test_the_workspace_state_directory_is_created_if_absent(self):
        fresh = self.tmp / "brand-new"
        episodes.record(fresh, unit="unit-1", path="p", excerpt="e",
                        verdict="PASS", evidence="ev")
        self.assertTrue((fresh / "mode-state").is_dir())


if __name__ == "__main__":
    unittest.main()
