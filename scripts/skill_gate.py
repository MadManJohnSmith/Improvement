"""Held-out gate for changes to the skill library.

The library has 55 scenarios with an expected verdict each, and the suite
asserts the corpus covers every skill in both directions. What it does not do
is run a scenario and compare what happened with what was supposed to happen,
which is the whole of what a change to a skill needs to be accepted or
refused: a scenario nobody executes cannot tell an improvement from a
regression.

This module is that decision and nothing else. The observations come from
outside, so the gate takes two result files and answers one question: does the
candidate beat the baseline on held-out scenarios without losing anything on
the rest?

The corpus is not yet runnable, which is a stronger obstacle than "no runtime".
Each `input` is a table of declarative assertions about a situation -- keys like
`contract_declared: true` or `attempted_write: true` -- not a task an agent can
be handed, and the files carry no `target_mode` and no prompt. Nothing can
execute them as written, so supplying a runtime would not by itself produce a
score: the scenarios have to be given an executable form first.

The form to copy already exists. `acceptance_harness._public_input` materializes
the same idea with a `task`, a bounded fixture and an `evaluated_claim`, and its
type vocabulary covers all eight types this corpus uses. The two corpora are
disconnected today -- nothing outside this module reads `library/`, and the
harness generates its own Host cases -- so wiring them together is authoring
work over a known template, not new machinery.

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


def evaluate_bound_gate(baseline_path, candidate_path, corpus_path,
                        baseline_digest, candidate_digest, val_fraction=0.3,
                        library=None):
    """Strict gate over complete observations bound to corpus and candidates."""
    import corpus_compiler

    corpus = corpus_compiler.load_corpus(corpus_path)
    baseline_payload, baseline = corpus_compiler.load_bound_observations(
        baseline_path, corpus, baseline_digest)
    candidate_payload, candidate = corpus_compiler.load_bound_observations(
        candidate_path, corpus, candidate_digest)
    reasons = []
    if (baseline_payload["provider"]["status"] != "available" or
            candidate_payload["provider"]["status"] != "available"):
        action = "abstain"
        reasons.append("provider unavailable; no execution evidence")
    else:
        scenarios = [{"scenario_id": case["case_id"],
                      "skill": case["target_skill"], "type": case["type"],
                      # The oracle remains Host-side; never part of public cases.
                      "expected": expected}
                     for case, expected in zip(corpus["cases"],
                         corpus_compiler.expected_verdicts(
                             library or Path(corpus_path).resolve().parent / "library",
                             corpus))]
        report = _evaluate_loaded(baseline, candidate, scenarios, val_fraction)
        action, reasons = report["action"], report["reasons"]
    result = {
        "schema_version": corpus_compiler.SCHEMA_VERSION,
        "compiler_version": corpus["compiler_version"],
        "corpus_digest": corpus["corpus_digest"],
        "baseline_candidate_digest": baseline_digest,
        "candidate_digest": candidate_digest,
        "action": action,
        "reasons": reasons,
    }
    return corpus_compiler.validate_bound_report(
        result, corpus["corpus_digest"], candidate_digest)


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


def _evaluate_loaded(baseline, candidate, scenarios, val_fraction=0.3):
    train, validation = split_scenarios(scenarios, val_fraction)
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
    # Unverifiable is empty, so every slice has a real accuracy to compare. The
    # explicit guard is what keeps an empty run abstaining: without it a missing
    # observation scored `None` and this line raised TypeError instead of
    # abstaining, which is the one thing a gate with no evidence must never do.
    if any(slice_ is None or slice_["accuracy"] is None
           for slice_ in (base_val, cand_val)):
        report.update({
            "action": "abstain",
            "reasons": ["faltan observaciones para comparar el holdout"],
        })
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


def evaluate_gate(baseline_path, candidate_path, library, val_fraction=0.3):
    """Legacy unbound gate retained for existing callers."""
    return _evaluate_loaded(load_observations(baseline_path),
                            load_observations(candidate_path),
                            load_scenarios(library), val_fraction)


def commit_trigger_check(changed_paths, report_path, corpus_digest,
                         candidate_digest):
    """Fail closed for relevant changes unless a bound report accepts them."""
    import corpus_compiler

    relevant = any(path == "library" or path.startswith(("library/", "scripts/skill_gate.py",
                   "scripts/corpus_compiler.py", "schemas/executable-corpus.schema.json",
                   "schemas/corpus-observations.schema.json",
                   "schemas/bound-gate-report.schema.json")) for path in changed_paths)
    if not relevant:
        return {"required": False, "accepted": True}
    if report_path is None:
        raise ValueError("relevant corpus changes require a bound accepting gate report")
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid gate report: {exc}") from exc
    corpus_compiler.validate_bound_report(report, corpus_digest, candidate_digest)
    if report["action"] != "accept":
        raise ValueError(f"bound gate did not accept: {report['action']}")
    return {"required": True, "accepted": True}
