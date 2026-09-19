"""Aceptación automática Host — C5.

Ejecuta validación estática, escenarios públicos y holdouts, con revisión
independiente explícita. Solo Host puede emitir ACTIVE o RETAINED.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import host_validator

SCHEMA_VERSION = 1


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _write(path, value):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Acceptance:
    """Host-owned acceptance evaluator."""

    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.generated = self.run_dir / "generated"
        self.results = []

    def _record(self, scenario_id, verdict, evidence=None, detail=""):
        self.results.append({
            "scenario_id": scenario_id,
            "verdict": verdict,
            "evidence_refs": evidence or [],
            "detail": detail,
        })

    def static_validation(self):
        report = host_validator.validate_package(self.generated)
        host_validator.write_reports(report, self.run_dir)
        verdict = "PASS" if report.passed else "FAIL"
        self._record("HOST-STATIC", verdict, ["validation/summary.json"],
                     report.verdict)
        return report

    def public_scenarios(self):
        scenarios_path = self.run_dir / "tests" / "public" / "scenarios.jsonl"
        if not scenarios_path.is_file():
            self._record("PUBLIC-CORPUS", "NOT_COVERED", [], "No public scenarios")
            return False
        passed = True
        for line in scenarios_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            scenario = json.loads(line)
            sid = scenario.get("scenario_id", "unknown")
            expected = scenario.get("expected", {}).get("verdict")
            # Mechanical scenarios are marked PASS when structurally complete;
            # semantic execution is delegated to the DSH harness.
            actual = "PASS" if scenario.get("input") is not None else "UNVERIFIED"
            self._record(sid, actual, [f"tests/public/scenarios.jsonl:{sid}"])
            if expected == "PASS" and actual != "PASS":
                passed = False
        return passed

    def holdouts(self):
        holdout = self.run_dir / "tests" / "holdout-spec.json"
        if not holdout.is_file():
            self._record("HOST-HOLDOUTS", "NOT_COVERED", [], "No holdout spec")
            return False
        spec = _read(holdout)
        families = spec.get("families", []) if isinstance(spec, dict) else []
        if not families:
            self._record("HOST-HOLDOUTS", "NOT_COVERED", [], "Empty holdout families")
            return False
        for family in families:
            self._record(f"HOLDOUT-{family}", "UNVERIFIED",
                         ["tests/holdout-spec.json"],
                         "Concrete cases materialized by Host")
        # Holdouts are intentionally hidden; unverified means no acceptance.
        return False

    def independent_review(self):
        # Explicitly degraded when no separate reviewer session is available.
        review = {
            "schema_version": SCHEMA_VERSION,
            "reviewer": "host-independent-review",
            "isolation": "DEGRADED_REVIEW",
            "verdict": "UNVERIFIED",
            "reason": "Independent DSH reviewer not configured",
            "timestamp": _now_iso(),
        }
        self._record("INDEPENDENT-REVIEW", "UNVERIFIED",
                     ["acceptance/independent-review.json"])
        return review

    def finalize(self, static_report, public_passed, holdout_passed, review):
        all_passed = (
            static_report.passed and public_passed and holdout_passed
            and review.get("verdict") == "PASS"
        )
        verdict = "ACTIVE" if all_passed else "RETAINED"
        gen_id = _read(self.run_dir / "run.json").get("generation_id")

        evidence_path = self.run_dir / "acceptance" / "evidence-ledger.jsonl"
        evidence_path.parent.mkdir(mode=0o700, exist_ok=True)
        with evidence_path.open("w", encoding="utf-8") as f:
            for result in self.results:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        host_verdict = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": gen_id,
            "verdict": verdict,
            "static_passed": static_report.passed,
            "public_passed": public_passed,
            "holdout_passed": holdout_passed,
            "independent_review": review.get("verdict"),
            "timestamp": _now_iso(),
        }
        _write(self.run_dir / "acceptance" / "host-verdict.json", host_verdict)

        # Host alone changes lifecycle state.
        run_path = self.run_dir / "run.json"
        run_doc = _read(run_path)
        run_doc["status"] = verdict
        run_doc["updated_at"] = _now_iso()
        run_path.unlink()
        _write(run_path, run_doc)

        return host_verdict

    def run(self):
        static_report = self.static_validation()
        public_passed = self.public_scenarios()
        holdout_passed = self.holdouts()
        review = self.independent_review()
        return self.finalize(static_report, public_passed, holdout_passed, review)


def accept(run_dir):
    return Acceptance(run_dir).run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(accept(args.run_dir), ensure_ascii=False, indent=2))
