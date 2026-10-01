"""Held-out gate for changes to the skill library.

The library has 55 scenarios with an expected verdict each, and the suite
asserts the corpus covers every skill in both directions. What it does not do
is run a scenario and compare what happened with what was supposed to happen,
which is the whole of what a change to a skill needs to be accepted or
refused: a scenario nobody executes cannot tell an improvement from a
regression.

This module is that decision and nothing else. The observations come from
outside — running scenarios against an agent needs a runtime — so the gate
takes two result files and answers one question: does the candidate beat the
baseline on held-out scenarios without losing anything on the rest?

Three properties are borrowed from SkillOpt's `evaluation/gate.py` because
they are easy to get wrong:

* a candidate is accepted only when it **strictly** improves the held-out
  score; equal is not better, and "no worse" is how a regression ships;
* a candidate that lowers the training score is refused even if the held-out
  score rises, because that is the shape of overfitting;
* when the validation slice is not disjoint from the slice the change was
  tuned on, the gate **abstains** instead of passing or failing. A gate that
  cannot prove anything says so loudly rather than returning a number.
"""

import hashlib
import json
from pathlib import Path

ACTIONS = ("accept", "reject", "abstain")


def load_scenarios(library):
    """Every scenario in the library, with the skill it belongs to."""
    library = Path(library)
    scenarios = []
    for path in sorted(library.glob("**/scenarios/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = record.get("scenario_id")
        expected = (record.get("expected") or {}).get("verdict")
        skill = record.get("target_skill") or path.parent.parent.name
        if not isinstance(scenario_id, str) or not isinstance(expected, str):
            raise ValueError(f"escenario incompleto: {path}")
        scenarios.append({
            "scenario_id": scenario_id,
            "skill": skill,
            "type": record.get("type", "unknown"),
            "expected": expected,
            "path": str(path.relative_to(library)),
        })
    if not scenarios:
        raise ValueError(f"la biblioteca no tiene escenarios: {library}")
    return scenarios


def split_scenarios(scenarios, val_fraction=0.3):
    """Deterministic train/validation split.

    The bucket is a digest of the scenario id, not a random draw: the same
    corpus always produces the same split, so a score today and a score next
    month are comparable and a change cannot be tuned on the set that judges
    it by re-rolling which scenarios land where.
    """
    if not 0.0 < val_fraction < 1.0:
        raise ValueError("val_fraction debe estar entre 0 y 1")
    train, validation = [], []
    for scenario in scenarios:
        bucket = int(hashlib.sha256(
            scenario["scenario_id"].encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        (validation if bucket < val_fraction else train).append(scenario)
    return train, validation


def load_observations(path):
    """Observed verdicts per scenario, from a run outside this module."""
    if path is None:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    observed = value.get("scenarios") if isinstance(value, dict) else None
    if not isinstance(observed, dict):
        raise ValueError(f"{path}: se esperaba {{'scenarios': {{id: veredicto}}}}")
    return observed


def score(observed, scenarios):
    """Accuracy over scenarios that were actually observed, and which were not."""
    if observed is None:
        return None
    correct, executed, missing = 0, 0, []
    for scenario in scenarios:
        result = observed.get(scenario["scenario_id"])
        if result is None:
            missing.append(scenario["scenario_id"])
            continue
        executed += 1
        correct += 1 if result == scenario["expected"] else 0
    return {"executed": executed, "correct": correct,
            "missing": missing,
            "accuracy": (correct / executed) if executed else None}


def _intersects(train, validation):
    train_ids = {scenario["scenario_id"] for scenario in train}
    return sorted(train_ids & {scenario["scenario_id"] for scenario in validation})


def evaluate_gate(baseline_path, candidate_path, library, val_fraction=0.3):
    """Accept the candidate only if it strictly improves held-out and holds the rest."""
    scenarios = load_scenarios(library)
    train, validation = split_scenarios(scenarios, val_fraction)
    baseline = load_observations(baseline_path)
    candidate = load_observations(candidate_path)
    base_train = score(baseline, train)
    base_val = score(baseline, validation)
    cand_train = score(candidate, train)
    cand_val = score(candidate, validation)

    report = {
        "corpus": {"scenarios": len(scenarios), "skills": len({s["skill"] for s in scenarios}),
                   "train": len(train), "validation": len(validation),
                   "val_fraction": val_fraction},
        "baseline": {"train": base_train, "validation": base_val},
        "candidate": {"train": cand_train, "validation": cand_val},
    }
    # Two kinds of reason, because they mean different things: a gate with no
    # evidence cannot judge and says so, while a gate that judged and found the
    # candidate worse refuses it.
    unverifiable, refusals = [], []
    if base_val is None or cand_val is None:
        unverifiable.append("faltan observaciones de validación")
    elif not cand_val["executed"]:
        unverifiable.append("ningún escenario de validación se ejecutó")
    if base_train is not None and cand_train is not None and cand_train["executed"]:
        if base_train["executed"] and cand_train["accuracy"] < base_train["accuracy"]:
            refusals.append(
                f"el candidato pierde en la partición de entrenamiento "
                f"({cand_train['accuracy']:.3f} < {base_train['accuracy']:.3f})")
    leaked = _intersects(train, validation)
    if leaked:
        unverifiable.append(f"la partición de validación no es disjunta: {leaked}")

    if unverifiable:
        report.update({"action": "abstain", "reasons": unverifiable + refusals})
        return report
    if refusals:
        report.update({"action": "reject", "reasons": refusals})
        return report
    improved = cand_val["accuracy"] > base_val["accuracy"]
    report.update({
        "action": "accept" if improved else "reject",
        "reasons": ([] if improved else
                    [f"el holdout no mejora estrictamente "
                     f"({cand_val['accuracy']:.3f} <= {base_val['accuracy']:.3f})"]),
        "delta": {
            "validation": cand_val["accuracy"] - base_val["accuracy"],
            "train": (cand_train["accuracy"] - base_train["accuracy"])
            if base_train and cand_train and base_train["accuracy"] is not None
            and cand_train["accuracy"] is not None else None,
        },
    })
    return report