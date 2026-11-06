"""Núcleo del evaluador de Creator: veredicto cerrado sobre artefactos registrados."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import creator_eval


def _facts(**overrides):
    facts = {
        "generation_id": "gen-test",
        "model": "provider/model",
        "project": {"root_identity": "a" * 64},
        "manifest_present": True,
        "prevalidation_passed": True,
        "journal_event_count": 3,
        "journal_last_seq": 2,
        "usage_tokens": 1000,
        "usage_input_tokens": 200,
        "usage_cache_read_tokens": 700,
        "usage_output_tokens": 100,
        "usage_steps": 4,
        "elapsed_seconds": 12.5,
    }
    facts.update(overrides)
    return facts


def _call(seq, name, arguments):
    return {"type": "tool/call", "seq": seq,
            "data": {"name": name, "arguments": json.dumps(arguments)}}


def _run(events, **overrides):
    seqs = [event["seq"] for event in events
            if isinstance(event.get("seq"), int)]
    facts = _facts(journal_event_count=len(events),
                   journal_last_seq=max(seqs) if seqs else 0)
    facts.update(overrides)
    return facts


def _criteria(**overrides):
    criteria = {
        "id": "case",
        "forbidden_schema_reads": ["modes.schema.json", "skills.schema.json"],
        "require_manifest": True,
        "require_prevalidation": True,
    }
    criteria.update(overrides)
    return criteria


class CreatorEvalGradeTest(unittest.TestCase):
    def test_a_complete_run_without_schema_reads_passes(self):
        """A run that finishes and never opens the two schemas meets the case."""
        events = [
            _call(0, "read", {"path": "product/src/main.py"}),
            _call(1, "bash", {"command":
                  "python3 -B /framework/scripts/read_view.py --root /framework "
                  "--path schemas/modes.schema.json --start 1 --end 20"}),
            _call(2, "bash", {"command": "ls generated"}),
        ]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["counts"]["schema_reads"], {})
        self.assertEqual(report["counts"]["reader_calls"], 1)

    def test_a_schema_read_after_a_complete_run_is_a_mechanism_failure(self):
        """Completion without the mechanism is its own verdict, not a pass."""
        events = [
            _call(0, "read", {"path": "/framework/schemas/modes.schema.json"}),
            _call(1, "read", {"path": "product/src/main.py"}),
        ]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["verdict"], "FAIL_MECHANISM")
        self.assertEqual(report["counts"]["schema_reads"],
                         {"modes.schema.json": 1})
        self.assertIn("modes.schema.json", report["reason"])

    def test_a_run_without_manifest_is_a_completion_failure(self):
        """A missing package is not a mechanism result; it is no result."""
        events = [
            _call(0, "read", {"path": "/framework/schemas/skills.schema.json"}),
        ]
        report = creator_eval.grade(
            _run(events, manifest_present=False), events, _criteria())
        self.assertEqual(report["verdict"], "FAIL_COMPLETION")
        self.assertIn("manifest", report["reason"])

    def test_a_run_with_failed_prevalidation_is_a_completion_failure(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(
            _run(events, prevalidation_passed=False), events, _criteria())
        self.assertEqual(report["verdict"], "FAIL_COMPLETION")

    def test_missing_model_abstains(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(
            _run(events, model=""), events, _criteria())
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("model", report["reason"])

    def test_missing_root_identity_abstains(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(
            _run(events, project={}), events, _criteria())
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("root_identity", report["reason"])

    def test_journal_count_mismatch_abstains(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(
            _run(events, journal_event_count=9), events, _criteria())
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("event_count", report["reason"])

    def test_last_seq_mismatch_abstains(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(
            _run(events, journal_last_seq=7), events, _criteria())
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("last_seq", report["reason"])

    def test_journal_without_tool_calls_abstains(self):
        """An empty or message-only journal is not a clean run."""
        events = [{"type": "assistant/message", "seq": 0, "data": {}}]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("herramienta", report["reason"])

    def test_schema_basename_needs_a_path_boundary(self):
        """`my_modes.schema.json` is not the schema; the exact path is."""
        events = [
            _call(0, "read", {"path": "product/my_modes.schema.json"}),
            _call(1, "read", {"path": "product/modes.schema.json.bak"}),
            _call(2, "read", {"path": "/framework/schemas/modes.schema.json"}),
        ]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["counts"]["schema_reads"],
                         {"modes.schema.json": 1})

    def test_reader_calls_are_counted_by_script_name(self):
        events = [
            _call(0, "bash", {"command": "python3 -B scripts/read_view.py --root . --path a"}),
            _call(1, "bash", {"command": "python3 -B scripts/read_view.py --root . --path b"}),
            _call(2, "bash", {"command": "grep read_view README.md"}),
        ]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["counts"]["reader_calls"], 2)

    def test_unknown_event_types_are_reported_not_fatal(self):
        events = [
            _call(0, "read", {"path": "product/src/main.py"}),
            {"type": "future/frame", "seq": 1, "data": {}},
        ]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(report["verdict"], "PASS")
        self.assertIn("future/frame", report["unknown_types"])

    def test_invalid_criteria_raise_value_error(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        with self.assertRaises(ValueError):
            creator_eval.grade(_run(events), events, {"id": "case"})

    def test_grade_is_deterministic(self):
        events = [
            _call(0, "read", {"path": "/framework/schemas/skills.schema.json"}),
            _call(1, "read", {"path": "/framework/schemas/modes.schema.json"}),
        ]
        first = creator_eval.grade(_run(events), events, _criteria())
        second = creator_eval.grade(_run(events), events, _criteria())
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_descriptive_metrics_report_cache_share(self):
        events = [_call(0, "read", {"path": "product/src/main.py"})]
        report = creator_eval.grade(_run(events), events, _criteria())
        self.assertAlmostEqual(report["descriptive"]["cache_share"], 0.7)
        self.assertEqual(report["descriptive"]["usage_tokens"], 1000)
