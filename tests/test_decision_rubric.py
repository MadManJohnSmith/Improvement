"""Regression for the versioned decision rubric and the gated proposal it binds
(issue #29, Phase 1 of the System 1 decision channel).

Without a rubric digest a proposal is not auditable: there is no proof of the
criterion that produced it. These cases pin the four ways this rot could return
-- a rubric published without a validator (E16's disease), a digest that
changes under re-serialization or survives a content change, a report that
cites a rubric half-way or echoes a threshold the rubric did not decide, and
`declared` confidence authorizing a fusion it never calibrated for. The
deterministic layer of the dedup pilot (exact signature => repeat, no channel)
is pinned end to end over a synthetic ledger: the memory, not the model, does
the classifying.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus_compiler
import episodes
import generation_contracts as gc


def _golden_rubric():
    return {
        "schema_version": 1,
        "rubric_id": "same-defect-pilot-1",
        "question": "same_defect",
        "options": ["same", "different"],
        "abstention": "insufficient",
        "thresholds": {"default": 0.7, "same_defect:2": 0.85},
        "confidence_provenance": "logits",
    }


def _golden_report(rubric=None, provenance="logits"):
    rubric = rubric or _golden_rubric()
    return {
        "schema_version": corpus_compiler.SCHEMA_VERSION,
        "compiler_version": corpus_compiler.COMPILER_VERSION,
        "corpus_digest": "a" * 64,
        "baseline_candidate_digest": "b" * 64,
        "candidate_digest": "c" * 64,
        "action": "abstain",
        "reasons": ["sin numero calibrado utilizable"],
        "rubric_sha256": gc.rubric_fingerprint(rubric),
        "threshold_echo": rubric["thresholds"]["same_defect:2"],
        "provenance": provenance,
    }


class DecisionRubricSchemaTest(unittest.TestCase):
    """The rubric is a validated artifact with a validator by its exact name."""

    def test_golden_rubric_validates_and_the_union_names_it_exactly(self):
        gc.validate("decision-rubric", _golden_rubric())
        # E16: the binding is declared in the product and named exactly; the
        # directory bijection itself is pinned in test_architecture_consistency.
        self.assertIs(gc.schema_enforcement("decision-rubric"),
                      gc.validate_decision_rubric)

    def test_schema_file_enums_align_with_the_validator(self):
        schema = json.loads(
            (ROOT / "schemas" / "decision-rubric.schema.json").read_text())
        properties = schema["properties"]
        self.assertEqual(set(properties["question"]["enum"]),
                         set(gc.RUBRIC_QUESTIONS))
        self.assertEqual(set(properties["options"]["items"]["enum"]),
                         set(gc.RUBRIC_OPTIONS))
        self.assertEqual(properties["abstention"]["enum"],
                         [gc.RUBRIC_ABSTENTION])
        self.assertEqual(properties["confidence_provenance"]["enum"],
                         [gc.RUBRIC_CALIBRATED_PROVENANCE])
        # The digest is not required content: an instance without it is the
        # form the Host fingerprints, and the pattern is the shared one.
        self.assertNotIn("digest", schema["required"])

    def test_rejects_unknown_field(self):
        doc = _golden_rubric()
        doc["min_confidence"] = 0.5
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)

    def test_rejects_open_answer_set(self):
        doc = _golden_rubric()
        doc["options"] = ["same", "different", "unclear"]
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)

    def test_rejects_an_unreachable_bucket(self):
        doc = _golden_rubric()
        doc["thresholds"]["same_defect:3"] = 0.9
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)

    def test_rejects_missing_default_threshold(self):
        doc = _golden_rubric()
        doc["thresholds"] = {"same_defect:2": 0.85}
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)

    def test_rejects_threshold_outside_unit_interval(self):
        doc = _golden_rubric()
        doc["thresholds"]["default"] = 1.2
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)

    def test_rejects_declared_as_calibrated_provenance(self):
        doc = _golden_rubric()
        doc["confidence_provenance"] = "declared"
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", doc)


class RubricDigestTest(unittest.TestCase):
    """The digest is the capabilities.fingerprint recipe: stable under
    re-serialization, changed by any content change, and never fed itself."""

    def test_digest_is_stable_under_re_serialization(self):
        digest = gc.rubric_fingerprint(_golden_rubric())
        shuffled = json.loads(json.dumps(_golden_rubric(), sort_keys=True))
        self.assertEqual(gc.rubric_fingerprint(shuffled), digest)

    def test_digest_changes_with_content(self):
        base = gc.rubric_fingerprint(_golden_rubric())
        changed = _golden_rubric()
        changed["thresholds"]["default"] = 0.75
        self.assertNotEqual(gc.rubric_fingerprint(changed), base)
        renamed = _golden_rubric()
        renamed["rubric_id"] = "same-defect-pilot-2"
        self.assertNotEqual(gc.rubric_fingerprint(renamed), base)

    def test_declared_digest_must_match_content(self):
        doc = _golden_rubric()
        doc["digest"] = gc.rubric_fingerprint(doc)
        gc.validate("decision-rubric", doc)
        stale = _golden_rubric()
        stale["thresholds"]["default"] = 0.75
        stale["digest"] = gc.rubric_fingerprint(_golden_rubric())
        with self.assertRaises(gc.ContractError):
            gc.validate("decision-rubric", stale)


class GatedReportExtensionTest(unittest.TestCase):
    """The report gains rubric_sha256 + threshold_echo + provenance without
    breaking the v1 contract: old reports keep validating, extensions travel
    together or not at all."""

    def test_v1_report_still_validates(self):
        report = _golden_report()
        v1 = {k: v for k, v in report.items()
              if k not in corpus_compiler.RUBRIC_REPORT_FIELDS}
        corpus_compiler.validate_bound_report(
            v1, v1["corpus_digest"], v1["candidate_digest"])

    def test_extended_report_validates(self):
        report = _golden_report()
        corpus_compiler.validate_bound_report(
            report, report["corpus_digest"], report["candidate_digest"])

    def test_schema_file_keeps_v1_required_and_adds_the_trio_optional(self):
        schema = json.loads(
            (ROOT / "schemas" / "bound-gate-report.schema.json").read_text())
        self.assertEqual(
            set(schema["required"]),
            {"schema_version", "compiler_version", "corpus_digest",
             "baseline_candidate_digest", "candidate_digest", "action",
             "reasons"})
        self.assertEqual(set(schema["properties"]["provenance"]["enum"]),
                         set(corpus_compiler.PROVENANCES))
        digest_def = schema["properties"]["rubric_sha256"]["$ref"].split("/")[-1]
        self.assertEqual(schema["$defs"][digest_def]["pattern"],
                         "^[0-9a-f]{64}$")

    def test_a_half_cited_rubric_is_rejected(self):
        report = _golden_report()
        del report["provenance"]
        with self.assertRaisesRegex(
                corpus_compiler.CorpusError, "travel together"):
            corpus_compiler.validate_bound_report(
                report, report["corpus_digest"], report["candidate_digest"])

    def test_malformed_rubric_fields_are_rejected(self):
        for mutate in (lambda r: r.update(rubric_sha256="nothex"),
                       lambda r: r.update(threshold_echo=True),
                       lambda r: r.update(threshold_echo=1.5),
                       lambda r: r.update(provenance="guessed")):
            report = _golden_report()
            mutate(report)
            with self.assertRaises(corpus_compiler.CorpusError):
                corpus_compiler.validate_bound_report(
                    report, report["corpus_digest"], report["candidate_digest"])


class RubricBindingTest(unittest.TestCase):
    """The audit verifies the proposal against the rubric it cites: the digest
    is the current rubric's, the echoed threshold is the one the rubric
    decides, and only calibrated confidence authorizes fusion."""

    def setUp(self):
        self.rubric = _golden_rubric()
        self.report = _golden_report(self.rubric)

    def _binding(self, **mutate_report):
        report = {**self.report, **mutate_report}
        return corpus_compiler.verify_rubric_binding(report, self.rubric)

    def test_binding_holds_and_echoes_the_bucket_threshold(self):
        binding = self._binding(action="reject")
        self.assertEqual(binding["rubric_sha256"],
                         gc.rubric_fingerprint(self.rubric))
        self.assertEqual(binding["bucket"], "same_defect:2")
        self.assertEqual(binding["threshold_echo"], 0.85)
        self.assertTrue(binding["fusion_authorized"])

    def test_declared_confidence_never_authorizes_fusion(self):
        binding = self._binding(provenance="declared")
        self.assertFalse(binding["fusion_authorized"])

    def test_missing_rubric_citation_fails_closed(self):
        report = {k: v for k, v in self.report.items()
                  if k not in corpus_compiler.RUBRIC_REPORT_FIELDS}
        with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                    "rubric_sha256"):
            corpus_compiler.verify_rubric_binding(report, self.rubric)

    def test_digest_of_another_rubric_version_is_rejected(self):
        other = _golden_rubric()
        other["thresholds"]["default"] = 0.9
        with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                    "does not match the current rubric"):
            corpus_compiler.verify_rubric_binding(self.report, other)

    def test_an_echoed_threshold_the_rubric_did_not_decide_is_rejected(self):
        with self.assertRaisesRegex(corpus_compiler.CorpusError,
                                    "threshold echo"):
            self._binding(threshold_echo=0.5)

    def test_an_invalid_rubric_never_binds(self):
        broken = _golden_rubric()
        del broken["abstention"]
        with self.assertRaises(gc.ContractError):
            corpus_compiler.verify_rubric_binding(self.report, broken)


class DeterministicDedupePilotTest(unittest.TestCase):
    """The dry pilot's deterministic layer, as a canary: exact signature =>
    repeat, decided by the memory and without a channel. The dry run measured
    3 findings, 3 distinct signatures, and a second-round replay classified
    repeated 3/3 with 0 false news; any regression that turns a replay into
    new work fails here, and the semantic layer (same_defect over distinct
    signatures) stays out: it needs a decision model and is not manufactured."""

    FINDINGS = (
        ("A-01", "src/libreta/storage.py",
         "with open(self.ruta, 'w') as f: f.write(json.dumps(datos))"),
        ("A-02", "src/libreta/storage.py",
         "datos = json.loads(f.read())"),
        ("A-03", "src/libreta/indice.py",
         "self._fd = open(self.ruta, 'r')"),
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pilot-sistema1-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.workspace = self.tmp / "ws"
        self.workspace.mkdir()

    def _finding_fingerprint(self, path, excerpt):
        # The write tool's recipe, which the memory fallback reproduces
        # (pinned against the real driver in test_workflow_write_plugin).
        return episodes.signature(path, excerpt)

    def test_replay_of_an_identical_round_classifies_repeated_three_of_three(self):
        for unit, path, excerpt in self.FINDINGS:
            episodes.record(self.workspace, unit=unit, path=path,
                            excerpt=excerpt, verdict="PASS",
                            evidence="pytest: suite verde tras la reparación",
                            repair="aplicar el parche A-0x verificado")
        index = episodes.read_index(self.workspace)
        fingerprints = {self._finding_fingerprint(path, excerpt)
                        for _, path, excerpt in self.FINDINGS}
        self.assertEqual(len(fingerprints), 3, "expected 0 exact collisions")
        self.assertTrue(fingerprints <= set(index["signatures"]),
                        "the memory lost a signature it was told to keep")
        repeats = {}
        for unit, path, excerpt in self.FINDINGS:
            recalled = episodes.recall(
                self.workspace,
                fingerprint=self._finding_fingerprint(path, excerpt))
            self.assertEqual([e["unit"] for e in recalled], [unit])
            repeats[unit] = recalled[0]["unit"]
        self.assertEqual(len(repeats), 3, "0 false news, not a guessed count")

    def test_a_finding_the_memory_never_saw_is_not_invented_as_a_repeat(self):
        for unit, path, excerpt in self.FINDINGS:
            episodes.record(self.workspace, unit=unit, path=path,
                            excerpt=excerpt, verdict="PASS",
                            evidence="pytest: suite verde tras la reparación")
        fresh = self._finding_fingerprint("src/libreta/other.py",
                                          "return sum(notas) / len(notas)")
        self.assertEqual(
            episodes.recall(self.workspace, fingerprint=fresh), [])


if __name__ == "__main__":
    unittest.main()
