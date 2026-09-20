"""Aceptación automática Host — C5.

Materializa casos Host, ejecuta evaluación y revisión DSH en sesiones separadas,
valida evidencia y hashes, y emite ACTIVE o RETAINED. Creator y actores DSH
nunca deciden el lifecycle ni escriben en el run canónico.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import acceptance_harness as harness
from acceptance_reviewer import DshAcceptanceActors, tree_digest
import host_validator

SCHEMA_VERSION = 1
HOST_POLICY_VERSION = "acceptance-host-policy-v1"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _digest_file(path):
    return _digest_bytes(Path(path).read_bytes())


def _write(path, value):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _replace(path, value):
    path = Path(path)
    if path.exists():
        path.unlink()
    _write(path, value)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _public_expected(verdict):
    # The plan's expected verdict describes the mode behavior under the case
    # (including BLOCKED/NOT_COVERED). Evaluator PASS means that behavior is
    # explicitly represented by the candidate contract.
    return verdict in ("PASS", "BLOCKED", "NOT_COVERED")


def validate_host_verdict(path, generated, *, generation_id=None):
    """Validate an existing Host verdict and all candidate/result bindings."""
    path, generated = Path(path), Path(generated)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"host-verdict no disponible: {path}")
    verdict = _read(path)
    required = {
        "schema_version", "generation_id", "verdict", "static_passed",
        "public_passed", "holdout_passed", "independent_review",
        "candidate_digest", "manifest_digest", "public_results_digest",
        "holdout_results_digest", "review_digest", "host_policy_digest",
        "timestamp",
    }
    if set(verdict) != required:
        raise ValueError("host-verdict tiene campos inválidos")
    if verdict["schema_version"] != SCHEMA_VERSION:
        raise ValueError("host-verdict schema_version inválida")
    if generation_id and verdict["generation_id"] != generation_id:
        raise ValueError("host-verdict corresponde a otra generación")
    if verdict["verdict"] not in ("ACTIVE", "RETAINED"):
        raise ValueError("host-verdict verdict inválido")
    manifest = generated / "generation-manifest.json"
    if tree_digest(generated) != verdict["candidate_digest"]:
        raise ValueError("host-verdict obsoleto: cambió el candidato")
    if _digest_file(manifest) != verdict["manifest_digest"]:
        raise ValueError("host-verdict obsoleto: cambió el manifest")
    acceptance_dir = path.parent
    bound = {
        "public_results_digest": acceptance_dir / "public-results.json",
        "holdout_results_digest": acceptance_dir / "holdout-results.json",
        "review_digest": acceptance_dir / "independent-review.json",
    }
    for field, artifact in bound.items():
        if not artifact.is_file() or _digest_file(artifact) != verdict[field]:
            raise ValueError(f"host-verdict obsoleto: {field} no coincide")
    active = all((
        verdict["static_passed"], verdict["public_passed"],
        verdict["holdout_passed"], verdict["independent_review"] == "PASS",
    ))
    if (verdict["verdict"] == "ACTIVE") != active:
        raise ValueError("host-verdict contradice sus gates")
    return verdict


class Acceptance:
    """Host-owned acceptance evaluator."""

    def __init__(self, run_dir, *, actors=None, launch_dsh=False,
                 timeout_seconds=900):
        self.run_dir = Path(run_dir)
        self.generated = self.run_dir / "generated"
        self.acceptance_dir = self.run_dir / "acceptance"
        self.results = []
        self.actors = actors
        self.launch_dsh = launch_dsh
        self.timeout_seconds = timeout_seconds
        self.generation_id = _read(self.run_dir / "run.json").get("generation_id")
        self.candidate_digest = None
        self.host_policy_digest = _digest_bytes(
            HOST_POLICY_VERSION.encode("utf-8"))

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

    def materialize(self):
        materialized = harness.materialize_run(
            self.run_dir, self.host_policy_digest)
        if materialized["plan"]["generation_id"] != self.generation_id:
            raise ValueError("acceptance-plan corresponde a otra generación")
        return materialized

    def _candidate_payload(self, materialized):
        """Load all reviewable candidate contracts without naming assumptions."""
        candidate = {}
        contracts = {}
        total_bytes = 0
        max_bytes = 2 * 1024 * 1024
        for path in sorted(self.generated.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlink no permitido en candidato: {path}")
            if not path.is_file():
                continue
            relative = str(path.relative_to(self.generated))
            if path.suffix == ".json":
                value = _read(path)
            elif path.name == "SKILL.md" or path.suffix == ".md":
                value = path.read_text(encoding="utf-8")
            elif path.suffix == ".jsonl":
                value = [json.loads(line) for line in path.read_text(
                    encoding="utf-8").splitlines() if line.strip()]
            else:
                continue
            encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
            total_bytes += len(encoded)
            if total_bytes > max_bytes:
                raise ValueError("Candidato excede 2 MiB de contexto de aceptación")
            if relative.startswith("contracts/"):
                contracts[relative] = value
            else:
                candidate[relative] = value
        if not candidate and not contracts:
            raise ValueError("Candidato sin contenido revisable")
        return candidate, contracts

    def _evaluate(self, actors, materialized):
        modes, contracts = self._candidate_payload(materialized)
        prompt = harness.build_evaluator_prompt(
            modes, contracts, materialized["public_cases"],
            materialized["holdout_cases"])
        expected_ids = [case["scenario_id"] for case in materialized["public_cases"]]
        expected_ids += [case["case_id"] for case in materialized["holdout_cases"]]
        payload = {
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "cases": [
                {"case_id": case_id} for case_id in expected_ids
            ],
        }
        observation = actors.evaluate(payload, prompt)
        envelope = observation["result"]
        results = harness.validate_evaluator_results(
            {"results": envelope["results"]}, expected_ids)
        return observation, results

    def _grade(self, materialized, results):
        public_count = len(materialized["public_cases"])
        public_observed = results[:public_count]
        holdout_observed = results[public_count:]
        public_rows = []
        public_passed = True
        for case, observed in zip(materialized["public_cases"], public_observed):
            expected_supported = _public_expected(case["expected"]["verdict"])
            passed = expected_supported and observed["verdict"] == "PASS"
            public_passed = public_passed and passed
            row = {
                "case_id": case["scenario_id"],
                "expected": case["expected"]["verdict"],
                "observed": observed["verdict"],
                "passed": passed,
                "evidence": observed["evidence"],
                "detail": observed["detail"],
            }
            public_rows.append(row)
            self._record(case["scenario_id"], "PASS" if passed else "FAIL",
                         observed["evidence"] if isinstance(observed["evidence"], list)
                         else [observed["evidence"]], observed["detail"])

        holdout_rows = []
        holdout_passed = True
        for case, observed in zip(materialized["holdout_cases"], holdout_observed):
            oracle = materialized["holdout_oracles"][case["case_id"]]
            # Holdout grading is Host-owned and predicate-based. The free-form
            # PASS/FAIL verdict is intentionally irrelevant here; unresolved
            # decisions fail closed because they do not equal the oracle.
            passed = observed["decision"] == oracle["expected_decision"]
            holdout_passed = holdout_passed and passed
            # Persist only the opaque grade. Keeping the evaluator decision next
            # to ``passed`` would disclose the hidden expected decision by simple
            # inversion, even though the oracle itself never reaches disk.
            holdout_rows.append({
                "case_id": case["case_id"],
                "family": case["family"],
                "passed": passed,
                "evidence": ["host-private-evaluation"],
                "detail": "Evaluator classification and rationale withheld after Host grading.",
            })
            # The ledger points to a neutral private-evaluation marker rather than
            # preserving rationale that could restate the discarded decision.
            self._record(case["case_id"], "PASS" if passed else "FAIL",
                         ["host-private-evaluation"], "Host holdout graded")
        return public_passed, public_rows, holdout_passed, holdout_rows

    def _review(self, actors, public_rows):
        public_summary = {
            "cases": [{
                "case_id": row["case_id"], "passed": row["passed"],
                "evidence": row["evidence"], "detail": row["detail"],
            } for row in public_rows],
        }
        prompt = harness.build_reviewer_prompt(
            self.candidate_digest, public_summary)
        expected_ids = [row["case_id"] for row in public_rows]
        payload = {
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "cases": [{"case_id": case_id} for case_id in expected_ids],
        }
        observation = actors.review(payload, prompt)
        result = observation["result"]
        if observation["session_id"] == getattr(self, "evaluator_session", None):
            raise ValueError("Revisor independiente reutilizó la sesión evaluator")
        review_rows = harness.validate_reviewer_results(
            {"results": result["results"]}, expected_ids)
        passed = (result["verdict"] == "PASS"
                  and all(row["verdict"] == "PASS" for row in review_rows))
        evidence = []
        for row in review_rows:
            refs = row["evidence"] if isinstance(row["evidence"], list) else [row["evidence"]]
            evidence.extend(refs)
        review = {
            "schema_version": SCHEMA_VERSION,
            "reviewer": "host-independent-reviewer",
            "session_id": observation["session_id"],
            "isolation": "SEPARATE_DSH_SESSION",
            "candidate_digest": self.candidate_digest,
            "verdict": "PASS" if passed else "FAIL",
            "evidence": sorted(set(evidence)),
            "results": review_rows,
            "summary": result["summary"],
            "timestamp": _now_iso(),
        }
        self._record("INDEPENDENT-REVIEW", review["verdict"],
                     review["evidence"], result["summary"])
        return review

    def _write_outputs(self, public_rows, holdout_rows, review):
        public_doc = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "results": public_rows,
        }
        holdout_doc = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "results": holdout_rows,
        }
        _replace(self.acceptance_dir / "public-results.json", public_doc)
        _replace(self.acceptance_dir / "holdout-results.json", holdout_doc)
        _replace(self.acceptance_dir / "independent-review.json", review)
        ledger = self.acceptance_dir / "evidence-ledger.jsonl"
        if ledger.exists():
            ledger.unlink()
        ledger.parent.mkdir(mode=0o700, exist_ok=True)
        with ledger.open("x", encoding="utf-8") as stream:
            for result in self.results:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")

    def finalize(self, static_report, public_passed, holdout_passed, review):
        all_passed = (
            static_report.passed and public_passed and holdout_passed
            and review.get("verdict") == "PASS"
        )
        verdict_name = "ACTIVE" if all_passed else "RETAINED"
        manifest_path = self.generated / "generation-manifest.json"
        host_verdict = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "verdict": verdict_name,
            "static_passed": static_report.passed,
            "public_passed": public_passed,
            "holdout_passed": holdout_passed,
            "independent_review": review.get("verdict"),
            "candidate_digest": self.candidate_digest,
            "manifest_digest": _digest_file(manifest_path),
            "public_results_digest": _digest_file(self.acceptance_dir / "public-results.json"),
            "holdout_results_digest": _digest_file(self.acceptance_dir / "holdout-results.json"),
            "review_digest": _digest_file(self.acceptance_dir / "independent-review.json"),
            "host_policy_digest": self.host_policy_digest,
            "timestamp": _now_iso(),
        }
        _replace(self.acceptance_dir / "host-verdict.json", host_verdict)
        validate_host_verdict(
            self.acceptance_dir / "host-verdict.json", self.generated,
            generation_id=self.generation_id)

        run_path = self.run_dir / "run.json"
        run_doc = _read(run_path)
        run_doc["status"] = verdict_name
        run_doc["updated_at"] = _now_iso()
        _replace(run_path, run_doc)
        return host_verdict

    def run(self):
        static_report = self.static_validation()
        materialized = self.materialize()
        self.candidate_digest = tree_digest(self.generated)
        actors_ctx = self.actors or DshAcceptanceActors(
            self.run_dir, launch=self.launch_dsh,
            timeout_seconds=self.timeout_seconds)
        owns_context = self.actors is None
        if owns_context:
            actors_ctx.__enter__()
        try:
            evaluator, results = self._evaluate(actors_ctx, materialized)
            self.evaluator_session = evaluator["session_id"]
            public_passed, public_rows, holdout_passed, holdout_rows = self._grade(
                materialized, results)
            review = self._review(actors_ctx, public_rows)
            if tree_digest(self.generated) != self.candidate_digest:
                raise ValueError("El candidato cambió durante aceptación")
            self._write_outputs(public_rows, holdout_rows, review)
            return self.finalize(
                static_report, public_passed, holdout_passed, review)
        finally:
            if owns_context:
                actors_ctx.__exit__(None, None, None)


def accept(run_dir, *, actors=None, launch_dsh=False, timeout_seconds=900):
    return Acceptance(
        run_dir, actors=actors, launch_dsh=launch_dsh,
        timeout_seconds=timeout_seconds).run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--launch-dsh", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        accept(args.run_dir, launch_dsh=args.launch_dsh),
        ensure_ascii=False, indent=2))
