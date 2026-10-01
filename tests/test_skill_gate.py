"""Regression for the held-out gate that judges a change to the skill library.

The corpus already asserts coverage; nothing ran it. These cases are the ones
that decide whether a library change ships, so each of them is a way the gate
could wave through a regression: a candidate that does not strictly improve, a
candidate that wins held-out while losing the rest, a validation slice that is
not disjoint, and observations that never arrived.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import skill_gate


def _corpus(tmp, scenarios):
    library = Path(tmp) / "library"
    for skill, records in scenarios.items():
        directory = library / "base" / skill / "scenarios"
        directory.mkdir(parents=True)
        for index, record in enumerate(records):
            (directory / f"SC-{index:03d}.json").write_text(json.dumps(record))
    return library


def _observation(scenarios, wrong=()):
    return {"scenarios": {
        record["scenario_id"]: ("FAIL" if record["scenario_id"] in wrong
                                else record["expected"]["verdict"])
        for records in scenarios.values() for record in records}}


class SkillGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scenarios = {
            "alpha": [{"scenario_id": f"A-{index}", "target_skill": "alpha",
                       "type": "positive",
                       "expected": {"verdict": "PASS"}} for index in range(6)],
            "beta": [{"scenario_id": f"B-{index}", "target_skill": "beta",
                      "type": "negative",
                      "expected": {"verdict": "BLOCKED"}} for index in range(6)],
        }
        self.library = _corpus(self.tmp.name, self.scenarios)

    def _run(self, baseline, candidate, val_fraction=0.4):
        base_path = Path(self.tmp.name) / "baseline.json"
        cand_path = Path(self.tmp.name) / "candidate.json"
        base_path.write_text(json.dumps(baseline))
        cand_path.write_text(json.dumps(candidate))
        return skill_gate.evaluate_gate(base_path, cand_path, self.library, val_fraction)

    def test_split_is_disjoint_and_deterministic(self):
        loaded = skill_gate.load_scenarios(self.library)
        first = skill_gate.split_scenarios(loaded, 0.4)
        second = skill_gate.split_scenarios(loaded, 0.4)
        self.assertEqual([s["scenario_id"] for s in first[0]],
                         [s["scenario_id"] for s in second[0]])
        self.assertEqual(skill_gate._intersects(first[0], first[1]), [])
        total = len(first[0]) + len(first[1])
        self.assertEqual(total, len(loaded))

    def test_candidate_is_accepted_only_when_it_strictly_improves(self):
        scenarios = self.scenarios
        # The improvement has to land in the held-out partition: fixing only
        # what the change was tuned on is exactly what the gate must not buy.
        loaded = skill_gate.load_scenarios(self.library)
        _, validation = skill_gate.split_scenarios(loaded, 0.4)
        wrong = [scenario["scenario_id"] for scenario in validation[:2]]
        baseline = _observation(scenarios, wrong=wrong)
        perfect = _observation(scenarios)
        report = self._run(baseline, perfect)
        self.assertEqual(report["action"], "accept", report["reasons"])
        self.assertGreater(report["delta"]["validation"], 0)

        # Equal is not better: the same performance is a rejection, because
        # "no worse" is how a regression ships under a different wording.
        self.assertEqual(self._run(baseline, baseline)["action"], "reject")

        worse = _observation(scenarios, wrong=wrong + ["A-1"])
        self.assertEqual(self._run(baseline, worse)["action"], "reject")

    def test_gate_abstains_when_observations_are_missing(self):
        """A gate with nothing to judge says so instead of returning a number.

        Scenarios that were never executed are not failures and they are not
        passes: they are the absence of evidence, and a holdout that produced
        none cannot license a change.
        """
        scenarios = self.scenarios
        report = self._run(_observation(scenarios), {"scenarios": {}})
        self.assertEqual(report["action"], "abstain")
        self.assertTrue(any("validación" in reason for reason in report["reasons"]))
        self.assertIsNone(report["candidate"]["validation"]["accuracy"])

        # And the detector for a split that is not disjoint is what would stop
        # a change tuned on the very set that judges it.
        loaded = skill_gate.load_scenarios(self.library)
        train, validation = skill_gate.split_scenarios(loaded, 0.4)
        self.assertEqual(skill_gate._intersects(train, validation), [])

    def test_gate_refuses_a_candidate_that_only_wins_by_losing_the_rest(self):
        scenarios = self.scenarios
        loaded = skill_gate.load_scenarios(self.library)
        train, validation = skill_gate.split_scenarios(loaded, 0.4)
        train_ids = [scenario["scenario_id"] for scenario in train]
        val_ids = [scenario["scenario_id"] for scenario in validation]
        baseline = {sid: "PASS" for sid in train_ids}
        baseline.update({sid: "FAIL" if sid in val_ids else "PASS" for sid in val_ids})
        # Candidate fixes the validation slice and breaks three training ones.
        candidate = dict(baseline)
        for sid in train_ids[:3]:
            candidate[sid] = "FAIL"
        for sid in val_ids:
            candidate[sid] = "PASS"
        report = self._run({"scenarios": baseline}, {"scenarios": candidate})
        self.assertEqual(report["action"], "reject", report)
        self.assertTrue(any("entrenamiento" in reason for reason in report["reasons"]))

    def test_gate_abstains_instead_of_raising_when_one_side_has_no_holdout(self):
        """One-sided evidence must abstain, not raise.

        When the baseline observed only the training slice, its validation
        accuracy is ``None`` while the candidate's is a real float. The abstain
        decision was made by an earlier check and then execution still fell
        through to ``float > None``, raising TypeError. A gate with nothing to
        compare failing with a stack trace is the worst possible answer: it
        reads as a broken tool rather than a gate that correctly refuses to
        judge, and it happens exactly when a run was incomplete.
        """
        loaded = skill_gate.load_scenarios(self.library)
        train, _ = skill_gate.split_scenarios(loaded, 0.4)
        train_only = {"scenarios": {x["scenario_id"]: "PASS" for x in train}}
        full = _observation(self.scenarios)
        report = self._run(train_only, full)
        self.assertEqual(report["action"], "abstain", report)
        self.assertTrue(report["reasons"], report)
        self.assertIsNone(report["baseline"]["validation"]["accuracy"], report)
        # The mirror image: a candidate that never reached the holdout.
        mirrored = self._run(full, train_only)
        self.assertEqual(mirrored["action"], "abstain", mirrored)

    def test_real_library_corpus_loads_and_splits(self):
        loaded = skill_gate.load_scenarios(ROOT / "library")
        self.assertGreaterEqual(len(loaded), 50)
        train, validation = skill_gate.split_scenarios(loaded, 0.3)
        self.assertGreater(len(train), 0)
        self.assertGreater(len(validation), 0)
        self.assertEqual(skill_gate._intersects(train, validation), [])
        self.assertEqual(skill_gate.score(None, loaded), None)


if __name__ == "__main__":
    unittest.main()