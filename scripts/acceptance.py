"""Aceptación determinista y veraz propiedad del Host.

Valida estáticamente el paquete y su plan, conserva bindings de candidato y
política, y emite READY_FOR_INSTALL o RETAINED. No crea sesiones DSH evaluator,
reviewer ni descendientes y no afirma haber ejecutado holdouts dinámicos.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import acceptance_harness as harness
from acceptance_reviewer import tree_digest
import host_validator

SCHEMA_VERSION = 1
HOST_POLICY_VERSION = "acceptance-host-policy-v1"
EARLY_RETAINED_NAME = "static-retained.json"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _digest_file(path):
    return _digest_bytes(Path(path).read_bytes())


def current_host_policy_digest():
    """Digest the current Host policy from its authoritative version source."""
    return _digest_bytes(HOST_POLICY_VERSION.encode("utf-8"))


def _retained_candidate_digest(root):
    """Bind rejected trees too, including symlinks static validation found."""
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries.append({
                "path": relative,
                "kind": "symlink",
                "target": os.readlink(path),
            })
        elif path.is_file():
            entries.append({
                "path": relative,
                "kind": "file",
                "sha256": _digest_file(path),
                "size_bytes": path.stat().st_size,
            })
    return _digest_bytes(json.dumps(
        entries, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _write(path, value):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _replace(path, value):
    """Atomically replace Host-owned JSON and reject symlink destinations."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Artefacto Host es enlace simbólico: {path}")
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _public_expected(expected_behavior):
    """Return whether a declared public behavior may satisfy the Host gate.

    ``expected_behavior`` describes what the case expects the candidate to do;
    it is not the evaluator's quality verdict. PASS, BLOCKED and NOT_COVERED
    are valid expected behaviors. Expected FAIL remains a fail-closed negative
    gate and cannot approve a candidate.
    """
    return expected_behavior in ("PASS", "BLOCKED", "NOT_COVERED")


def validate_early_retained(path, generated, *, generation_id=None):
    """Validate a Host early-retention record without acceptance artifacts."""
    path, generated = Path(path), Path(generated)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"static-retained no disponible: {path}")
    retained = _read(path)
    required = {
        "schema_version", "generation_id", "verdict", "stage", "reason",
        "candidate_digest", "manifest_digest", "validation_summary",
        "host_policy_digest", "timestamp",
    }
    if set(retained) != required:
        raise ValueError("static-retained tiene campos inválidos")
    if retained["schema_version"] != SCHEMA_VERSION:
        raise ValueError("static-retained schema_version inválida")
    if generation_id and retained["generation_id"] != generation_id:
        raise ValueError("static-retained corresponde a otra generación")
    if retained["verdict"] != "RETAINED":
        raise ValueError("static-retained verdict inválido")
    if retained["stage"] not in ("STATIC_VALIDATION", "ACCEPTANCE_PLAN"):
        raise ValueError("static-retained stage inválido")
    if retained["host_policy_digest"] != current_host_policy_digest():
        raise ValueError("static-retained obsoleto: cambió la política Host")
    if not isinstance(retained["reason"], str) or not retained["reason"].strip():
        raise ValueError("static-retained reason inválido")
    if _retained_candidate_digest(generated) != retained["candidate_digest"]:
        raise ValueError("static-retained obsoleto: cambió el candidato")
    manifest = generated / "generation-manifest.json"
    expected_manifest = (
        _digest_file(manifest) if manifest.is_file()
        and not manifest.is_symlink() else None)
    if retained["manifest_digest"] != expected_manifest:
        raise ValueError("static-retained obsoleto: cambió el manifest")
    summary = retained["validation_summary"]
    if not isinstance(summary, dict) or set(summary) != {"ref", "digest"}:
        raise ValueError("static-retained validation_summary inválido")
    summary_path = path.parent.parent / summary["ref"]
    if (summary_path.is_symlink() or not summary_path.is_file()
            or _digest_file(summary_path) != summary["digest"]):
        raise ValueError("static-retained obsoleto: validation summary no coincide")
    try:
        summary_doc = _read(summary_path)
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError(
            f"static-retained obsoleto: validation summary inválido: {error}") from error
    required_summary = {
        "schema_version", "generation_id", "candidate_digest",
        "manifest_digest", "verdict", "passed", "layers",
    }
    if set(summary_doc) != required_summary:
        raise ValueError("static-retained obsoleto: validation summary sin binding")
    expected_binding = {
        "generation_id": retained["generation_id"],
        "candidate_digest": retained["candidate_digest"],
        "manifest_digest": retained["manifest_digest"],
    }
    if any(summary_doc.get(field) != value
           for field, value in expected_binding.items()):
        raise ValueError(
            "static-retained obsoleto: validation summary corresponde a otro candidato")
    if (retained["stage"] == "STATIC_VALIDATION"
            and summary_doc.get("passed")):
        raise ValueError(
            "static-retained contradice un validation summary exitoso")
    if (retained["stage"] == "ACCEPTANCE_PLAN"
            and not summary_doc.get("passed")):
        raise ValueError(
            "static-retained de acceptance-plan requiere validación estática exitosa")
    layers = summary_doc.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise ValueError("static-retained obsoleto: validation summary sin capas")
    validation_dir = summary_path.parent
    for layer_name, layer_data in layers.items():
        layer_path = validation_dir / f"{layer_name}.json"
        if layer_path.is_symlink() or not layer_path.is_file():
            raise ValueError(
                f"static-retained obsoleto: falta reporte de capa {layer_name}")
        try:
            layer_doc = _read(layer_path)
        except (OSError, UnicodeError, ValueError) as error:
            raise ValueError(
                f"static-retained obsoleto: reporte {layer_name} inválido: {error}") from error
        expected_layer = {
            "schema_version", "generation_id", "candidate_digest",
            "manifest_digest", "layer", "passed", "details",
        }
        if set(layer_doc) != expected_layer:
            raise ValueError(
                f"static-retained obsoleto: reporte {layer_name} sin binding")
        if (layer_doc["layer"] != layer_name
                or layer_doc["passed"] != layer_data.get("passed")
                or layer_doc["details"] != layer_data.get("details")
                or any(layer_doc.get(field) != value
                       for field, value in expected_binding.items())):
            raise ValueError(
                f"static-retained obsoleto: reporte {layer_name} no coincide")
    return retained


def validate_host_verdict(path, generated, *, generation_id=None):
    """Validate an existing Host verdict and all candidate/result bindings."""
    path, generated = Path(path), Path(generated)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"host-verdict no disponible: {path}")
    verdict = _read(path)
    required = {
        "schema_version", "generation_id", "verdict", "static_passed",
        "acceptance_plan_valid", "dynamic_evaluation", "candidate_digest",
        "manifest_digest", "validation_summary_digest", "acceptance_plan_digest",
        "host_policy_digest", "timestamp",
    }
    if set(verdict) != required:
        raise ValueError("host-verdict tiene campos inválidos")
    if verdict["schema_version"] != SCHEMA_VERSION:
        raise ValueError("host-verdict schema_version inválida")
    if generation_id and verdict["generation_id"] != generation_id:
        raise ValueError("host-verdict corresponde a otra generación")
    if verdict["verdict"] not in ("READY_FOR_INSTALL", "RETAINED"):
        raise ValueError("host-verdict verdict inválido")
    if verdict["host_policy_digest"] != current_host_policy_digest():
        raise ValueError("host-verdict obsoleto: cambió la política Host")
    manifest = generated / "generation-manifest.json"
    if tree_digest(generated) != verdict["candidate_digest"]:
        raise ValueError("host-verdict obsoleto: cambió el candidato")
    if _digest_file(manifest) != verdict["manifest_digest"]:
        raise ValueError("host-verdict obsoleto: cambió el manifest")
    acceptance_dir = path.parent
    bound = {
        "validation_summary_digest": path.parent.parent / "validation" / "summary.json",
        "acceptance_plan_digest": generated / "acceptance-plan.json",
    }
    for field, artifact in bound.items():
        if not artifact.is_file() or _digest_file(artifact) != verdict[field]:
            raise ValueError(f"host-verdict obsoleto: {field} no coincide")
    ready = (verdict["static_passed"] and verdict["acceptance_plan_valid"]
             and verdict["dynamic_evaluation"] == "NOT_RUN")
    if (verdict["verdict"] == "READY_FOR_INSTALL") != ready:
        raise ValueError("host-verdict contradice sus gates deterministas")
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
        self.host_policy_digest = current_host_policy_digest()

    def _record(self, scenario_id, verdict, evidence=None, detail=""):
        self.results.append({
            "scenario_id": scenario_id,
            "verdict": verdict,
            "evidence_refs": evidence or [],
            "detail": detail,
        })

    def static_validation(self):
        report = host_validator.validate_package(
            self.generated, run_dir=self.run_dir)
        host_validator.write_reports(report, self.run_dir)
        verdict = "PASS" if report.passed else "FAIL"
        self._record("HOST-STATIC", verdict, ["validation/summary.json"],
                     report.verdict)
        return report

    def materialize(self):
        materialized = harness.materialize_run(
            self.run_dir, self.host_policy_digest)
        if materialized["plan"]["generation_id"] != self.generation_id:
            raise harness.HarnessError(
                "acceptance-plan corresponde a otra generación")
        return materialized

    def retain_early(self, static_report, *, stage, reason):
        """Persist a Host-only, resumable retention before dynamic acceptance."""
        self.candidate_digest = _retained_candidate_digest(self.generated)
        manifest_path = self.generated / "generation-manifest.json"
        summary_path = self.run_dir / "validation" / "summary.json"
        retained = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "verdict": "RETAINED",
            "stage": stage,
            "reason": reason,
            "candidate_digest": self.candidate_digest,
            "manifest_digest": (
                _digest_file(manifest_path) if manifest_path.is_file() else None),
            "host_policy_digest": self.host_policy_digest,
            "validation_summary": {
                "ref": "validation/summary.json",
                "digest": _digest_file(summary_path),
            },
            "timestamp": _now_iso(),
        }
        retained_path = self.acceptance_dir / EARLY_RETAINED_NAME
        _replace(retained_path, retained)
        validate_early_retained(
            retained_path, self.generated, generation_id=self.generation_id)

        run_path = self.run_dir / "run.json"
        run_doc = _read(run_path)
        run_doc["status"] = "RETAINED"
        run_doc["updated_at"] = _now_iso()
        _replace(run_path, run_doc)
        _replace(self.run_dir / "checkpoint.json", {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "phase": "RETAINED",
            "reason": reason,
            "retained_artifact": f"acceptance/{EARLY_RETAINED_NAME}",
            "completed_phases": [
                "preflight", "snapshot", "inventory", "skills",
                "creator_call", "generation", "validation",
            ],
            "pending_phases": ["repair", "acceptance", "activation"],
            "timestamp": _now_iso(),
            "resumable": True,
        })
        return retained

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

    @staticmethod
    def _canonical_public_detail(case, observed):
        subject_field, subject = harness._subject(
            case["input"], f"public case {case['scenario_id']!r}.input")
        return (
            f"Host {subject_field} {json.dumps(subject, ensure_ascii=False)}; "
            f"evaluator decision={observed['decision']}; "
            f"evaluator verdict={observed['verdict']}."
        )

    def _grade(self, materialized, results):
        public_count = len(materialized["public_cases"])
        public_observed = results[:public_count]
        holdout_observed = results[public_count:]
        public_rows = []
        public_passed = True
        for case, observed in zip(materialized["public_cases"], public_observed):
            expected_behavior = case["expected"]["verdict"]
            expected_decision = materialized["public_expected_decisions"][
                case["scenario_id"]]
            # ``expected_behavior`` is the scenario's desired behavior, while
            # evaluator PASS is a quality judgment: the candidate represents
            # that behavior correctly. Keep the structured Host decision as a
            # separate mandatory predicate. In particular, BLOCKED and
            # NOT_COVERED can pass with evaluator PASS, evaluator FAIL never
            # passes, and expected FAIL remains fail-closed by policy.
            passed = (_public_expected(expected_behavior)
                      and observed["verdict"] == "PASS"
                      and observed["decision"] == expected_decision)
            public_passed = public_passed and passed
            detail = self._canonical_public_detail(case, observed)
            row = {
                "case_id": case["scenario_id"],
                "claim_id": observed["claim_id"],
                "expected": case["expected"]["verdict"],
                "observed": observed["verdict"],
                "decision": observed["decision"],
                "expected_decision": expected_decision,
                "passed": passed,
                "evidence": observed["evidence"],
                "detail": detail,
            }
            public_rows.append(row)
            self._record(case["scenario_id"], "PASS" if passed else "FAIL",
                         observed["evidence"] if isinstance(observed["evidence"], list)
                         else [observed["evidence"]], detail)

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

    def _review(self, actors, public_cases, public_rows):
        cases = {case["scenario_id"]: case for case in public_cases}
        public_summary = {
            "cases": [{
                "case_id": row["case_id"],
                "claim_id": row["claim_id"],
                "subject": harness.public_subject(cases[row["case_id"]]),
                "input": cases[row["case_id"]]["input"],
                "decision": row["decision"],
                "expected_public_behavior": cases[row["case_id"]]["expected"],
                "expected_decision": row["expected_decision"],
                "passed": row["passed"],
                "evidence": row["evidence"],
            } for row in public_rows],
        }
        prompt = harness.build_reviewer_prompt(
            self.candidate_digest, public_summary)
        expected_ids = [row["case_id"] for row in public_rows]
        payload = {
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "cases": public_summary["cases"],
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
        try:
            static_report = self.static_validation()
        except OSError:
            raise
        except (ValueError, UnicodeError) as error:
            manifest_path = self.generated / "generation-manifest.json"
            static_report = host_validator.ValidationReport(
                self.generation_id,
                candidate_digest=_retained_candidate_digest(self.generated),
                manifest_digest=(
                    _digest_file(manifest_path) if manifest_path.is_file()
                    and not manifest_path.is_symlink() else None),
            )
            static_report.add_layer("static_input", False, [str(error)])
            host_validator.write_reports(static_report, self.run_dir)
        if not static_report.passed:
            return self.retain_early(
                static_report, stage="STATIC_VALIDATION",
                reason=(
                    "Static Host validation failed: "
                    f"{static_report.verdict}"))
        try:
            materialized = self.materialize()
        except harness.HarnessError as error:
            return self.retain_early(
                static_report, stage="ACCEPTANCE_PLAN", reason=str(error))
        self.candidate_digest = tree_digest(self.generated)
        if self.actors is not None:
            raise ValueError(
                "La aceptación vigente no admite evaluator/reviewer DSH")
        if tree_digest(self.generated) != self.candidate_digest:
            raise ValueError("El candidato cambió durante aceptación")
        manifest_path = self.generated / "generation-manifest.json"
        plan_path = self.generated / "acceptance-plan.json"
        summary_path = self.run_dir / "validation" / "summary.json"
        verdict = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "verdict": "READY_FOR_INSTALL",
            "static_passed": True,
            "acceptance_plan_valid": True,
            "dynamic_evaluation": "NOT_RUN",
            "candidate_digest": self.candidate_digest,
            "manifest_digest": _digest_file(manifest_path),
            "validation_summary_digest": _digest_file(summary_path),
            "acceptance_plan_digest": _digest_file(plan_path),
            "host_policy_digest": self.host_policy_digest,
            "timestamp": _now_iso(),
        }
        verdict_path = self.acceptance_dir / "host-verdict.json"
        _replace(verdict_path, verdict)
        validate_host_verdict(
            verdict_path, self.generated, generation_id=self.generation_id)
        return verdict


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
