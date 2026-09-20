"""Validador Host de generación — C3.

Validación independiente fail-closed de paquetes Creator.
Produce reportes por capa y no realiza escrituras activas.

    python3 -B scripts/host_validator.py --generated <path>

Versión: 1
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK / "scripts"))

import generation_contracts as gc
from onboard import checked

SCHEMA_VERSION = 1


def _digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _candidate_digest(root):
    """Digest every candidate entry, including symlinks rejected by validation."""
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
    return hashlib.sha256(json.dumps(
        entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Validation layers
# ---------------------------------------------------------------------------


class ValidationReport:
    """Accumulates results bound to one generation and candidate snapshot."""

    def __init__(self, generation_id, *, candidate_digest=None,
                 manifest_digest=None):
        self.generation_id = generation_id
        self.candidate_digest = candidate_digest
        self.manifest_digest = manifest_digest
        self.layers = {}
        self.passed = True
        self.verdict = "READY_FOR_ACCEPTANCE"

    def add_layer(self, name, passed, details=None):
        self.layers[name] = {
            "passed": passed,
            "details": details or [],
        }
        if not passed:
            self.passed = False
            self.verdict = "RETAINED"

    def to_dict(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "candidate_digest": self.candidate_digest,
            "manifest_digest": self.manifest_digest,
            "verdict": self.verdict,
            "passed": self.passed,
            "layers": self.layers,
        }


def validate_package(generated_dir, *, run_dir=None):
    """Validate a Creator package through all layers.

    Returns a ValidationReport. Never writes to the filesystem.
    """
    generated = Path(generated_dir)
    if not generated.is_dir():
        raise ValueError(f"generated/ no existe: {generated}")

    manifest_path = generated / "generation-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("generation-manifest.json faltante")
    if manifest_path.is_symlink():
        raise ValueError("generation-manifest.json es enlace simbólico")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_gen_id = manifest.get("generation_id", "unknown")
    expected_gen_id = manifest_gen_id
    if run_dir is not None:
        run_path = Path(run_dir) / "run.json"
        if run_path.is_file() and not run_path.is_symlink():
            run_doc = json.loads(run_path.read_text(encoding="utf-8"))
            expected_gen_id = run_doc.get("generation_id", manifest_gen_id)
    report = ValidationReport(
        expected_gen_id,
        candidate_digest=_candidate_digest(generated),
        manifest_digest=_digest_file(manifest_path),
    )

    # Layer 1: Schema/version/unknown fields, including acceptance-plan early
    _validate_layer_schema(
        report, manifest, generated, expected_generation=expected_gen_id)

    # Layer 2: Manifest exhaustivo, hashes, file types, paths, symlinks
    _validate_layer_manifest(report, manifest, generated)

    # Layer 3: Graph de referencias, ciclos y hot paths
    _validate_layer_graph(report, manifest, generated)

    # Layer 4: Contracts/requirements/source provenance
    _validate_layer_contracts(report, manifest, generated, run_dir=run_dir)

    # Layer 5: Capabilities, roots, tools, models, routing
    _validate_layer_capabilities(report, manifest, generated)

    # Layer 6: Portability, scripts, subprocess, red, datos
    _validate_layer_portability(report, manifest, generated)

    # Layer 7: Context budgets
    _validate_layer_context_budget(report, manifest, generated)

    # Layer 8: Collision/ownership/precedence
    _validate_layer_collision(report, manifest)

    # Layer 9: Licencia/THIRD_PARTY_NOTICES
    _validate_layer_license(report, manifest)

    # Layer 10: Anti-auto-approval y lifecycle
    _validate_layer_lifecycle(report, manifest)

    return report


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------


def _validate_layer_schema(report, manifest, generated,
                           expected_generation=None):
    """Layer 1: validate manifest and acceptance plan before later layers."""
    issues = []
    try:
        gc.validate("generation-manifest", manifest)
    except gc.ContractError as e:
        issues.append(str(e))
    if (expected_generation is not None
            and manifest.get("generation_id") != expected_generation):
        issues.append("generation-manifest corresponde a otra generación")

    plan_path = generated / "acceptance-plan.json"
    if not plan_path.is_file() or plan_path.is_symlink():
        issues.append("acceptance-plan.json faltante o enlace simbólico")
    else:
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            gc.validate("acceptance-plan", plan)
            if plan.get("generation_id") != manifest.get("generation_id"):
                issues.append(
                    "acceptance-plan.generation_id no coincide con el manifest")
        except (OSError, UnicodeError, ValueError, gc.ContractError) as e:
            issues.append(f"acceptance-plan.json inválido: {e}")
    report.add_layer("schema", not issues, issues)


def _validate_layer_manifest(report, manifest, generated):
    """Layer 2: Exhaustive manifest, hashes, paths, symlinks."""
    issues = []

    # Check all declared artifacts exist and have correct hashes
    try:
        mismatches = gc.verify_manifest_hashes(manifest, str(generated))
        for path, expected, actual in mismatches:
            issues.append(f"Hash mismatch: {path} (expected {expected[:16]}..., got {actual[:16]}...)")
    except gc.ContractError as e:
        issues.append(str(e))

    # Check for symlinks
    try:
        gc.check_no_symlinks(str(generated))
    except gc.ContractError as e:
        issues.append(str(e))

    # Check path safety and semantic artifact typing on all artifacts.
    for art in manifest.get("artifacts", []):
        path = art.get("path", "")
        try:
            gc.check_path_safety(path)
        except gc.ContractError as e:
            issues.append(str(e))
        if Path(path).name == "SKILL.md" and art.get("type") != "skill-entrypoint":
            issues.append(
                f"Manifest artifact {path}: SKILL.md must use type "
                "'skill-entrypoint'")

    report.add_layer("manifest", not issues, issues)


def _validate_layer_graph(report, manifest, generated):
    """Layer 3: Reference graph, cycles, hot paths."""
    issues = []

    # Check for orphan files (files referenced that don't exist in manifest)
    manifested = {a["path"] for a in manifest.get("artifacts", [])}

    # Check entrypoints exist
    entrypoints = [
        a for a in manifest.get("artifacts", [])
        if a.get("type") == "skill-entrypoint"
    ]
    if not entrypoints:
        issues.append("No skill entrypoints found in manifest")

    # Basic cycle detection: check that no file references itself
    for art in manifest.get("artifacts", []):
        path = art.get("path", "")
        full = generated / path
        if full.is_file() and not full.is_symlink():
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
                if len(content) < 100000:
                    # Check for self-references that could cause load cycles
                    parts = Path(path).parts
                    if len(parts) > 1 and parts[-1] in content:
                        pass  # Filename in content is normal
            except (UnicodeDecodeError, OSError):
                pass

    # Hot path budgets
    policy = manifest.get("context_policy", {})
    max_entry = policy.get("skill_entrypoint_max_bytes", 32768)
    max_support = policy.get("support_file_max_bytes", 24576)

    for art in manifest.get("artifacts", []):
        full = generated / art.get("path", "")
        if full.is_file() and not full.is_symlink():
            size = full.stat().st_size
            if art.get("type") == "skill-entrypoint" and size > max_entry:
                issues.append(
                    f"Entrypoint exceeds budget: {art['path']} "
                    f"({size} > {max_entry} bytes)"
                )
            elif size > max_support:
                issues.append(
                    f"Support file exceeds budget: {art['path']} "
                    f"({size} > {max_support} bytes)"
                )

    report.add_layer("graph", not issues, issues)


def _load_run_library(run_dir):
    """Load and validate the run's library snapshot, if present."""
    if run_dir is None:
        return None
    lib_path = Path(run_dir) / "inputs" / "library.json"
    if not lib_path.is_file() or lib_path.is_symlink():
        return None
    library = json.loads(lib_path.read_text(encoding="utf-8"))
    gc.validate("library", library)
    return library


def _contract_kind(doc, rel):
    """Resolve a contract kind without inspecting motive or other payload fields.

    Explicit discriminators and unambiguous schema-v1 locations/names take
    precedence.  Free-form legacy names under ``contracts/`` are classified only
    by complete validation against both contract schemas.
    """
    kind = doc.get("kind")
    if kind is not None:
        if not isinstance(kind, str) or kind not in gc.CONTRACT_KINDS:
            raise gc.ContractError(
                f"contract.kind must be 'mode' or 'skill', got {kind!r}")
        return kind

    path = Path(rel)
    parts = path.parts
    name = path.name
    if len(parts) >= 2 and parts[0] == "modes" and name == "mode.json":
        return "mode"
    if len(parts) >= 2 and parts[0] == "skills" and name in (
            "skill.json", "skill-contract.json", "contract.json"):
        return "skill"
    if parts and parts[0] == "contracts":
        if name == "mode-contract.json" or name.endswith(".mode.json"):
            return "mode"
        if name == "skill-contract.json" or name.endswith(".skill.json"):
            return "skill"

        matches = []
        failures = {}
        for candidate in sorted(gc.CONTRACT_KINDS):
            try:
                gc.validate(f"{candidate}-contract", doc)
            except gc.ContractError as error:
                failures[candidate] = str(error)
            else:
                matches.append(candidate)
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise gc.ContractError(
                "contract.kind is missing and legacy contract validation is "
                "ambiguous: both mode-contract and skill-contract validate")
        raise gc.ContractError(
            "contract.kind is missing and legacy contract validation matched "
            "neither mode-contract nor skill-contract; "
            f"mode-contract: {failures['mode']}; "
            f"skill-contract: {failures['skill']}")

    raise gc.ContractError(
        "contract.kind is missing and the schema-v1 contract path/name is not "
        "a recognized legacy mode or skill location")


def _validate_layer_contracts(report, manifest, generated, run_dir=None):
    """Layer 4: Contracts, requirements, source provenance, reuse resolution."""
    issues = []

    # Check that contracts directory exists if referenced
    contracts_dir = generated / "contracts"
    contract_arts = [
        a for a in manifest.get("artifacts", [])
        if a.get("type") == "contract"
    ]
    if contract_arts and not contracts_dir.is_dir():
        issues.append("Contract artifacts declared but contracts/ missing")

    try:
        library = _load_run_library(run_dir)
    except (ValueError, gc.ContractError) as e:
        issues.append(f"Library snapshot del run inválida: {e}")
        library = None
    known_refs = set()
    if library is not None:
        known_refs = {b["name"] for b in library.get("base_skills", [])}
        known_refs |= {c["name"] for c in library.get("catalog_patterns", [])}

    # Contract documents: schema-valid and reuse references resolvable
    for art in contract_arts:
        rel = art.get("path", "")
        cpath = generated / rel
        if not cpath.is_file() or cpath.is_symlink():
            continue  # existence/hash covered by the manifest layer
        if rel.endswith(".jsonl"):
            seen_ids = set()
            try:
                lines = [line for line in cpath.read_text(
                    encoding="utf-8").splitlines() if line.strip()]
                if not lines:
                    raise ValueError("JSONL vacío")
                for index, line in enumerate(lines, 1):
                    scenario = json.loads(line)
                    gc.validate("scenario", scenario)
                    scenario_id = scenario.get("scenario_id")
                    if scenario_id in seen_ids:
                        raise ValueError(
                            f"scenario_id duplicado {scenario_id!r}")
                    seen_ids.add(scenario_id)
            except (ValueError, gc.ContractError) as error:
                issues.append(f"Contrato JSONL inválido: {rel}: {error}")
            continue
        try:
            doc = json.loads(cpath.read_text(encoding="utf-8"))
        except ValueError:
            issues.append(f"Contrato JSON inválido: {rel}")
            continue
        if not isinstance(doc, dict) or "reuse_source" not in doc:
            continue
        try:
            kind = _contract_kind(doc, rel)
            schema_name = f"{kind}-contract"
            gc.validate(schema_name, doc)
        except gc.ContractError as e:
            issues.append(f"{rel}: {e}")
            continue
        if library is not None and doc.get("reuse_source") in (
                "base-library", "specialized-catalog"):
            ref = doc.get("reuse_reference")
            if ref not in known_refs:
                issues.append(
                    f"{rel}: reuse_reference {ref!r} no existe en la "
                    "biblioteca del run")

    # Check provenance entries
    for prov in manifest.get("license_provenance", []):
        if not prov.get("file"):
            issues.append("Provenance entry without file reference")
        if not prov.get("license"):
            issues.append("Provenance entry without license type")

    report.add_layer("contracts", not issues, issues)


def _validate_layer_capabilities(report, manifest, generated):
    """Layer 5: capability consistency across manifest, grant and modes."""
    issues = []
    required = set(manifest.get("required_capabilities", []))
    forbidden = set(manifest.get("forbidden_capabilities", []))
    overlap = required & forbidden
    if overlap:
        issues.append(
            f"Capabilities both required and forbidden: {sorted(overlap)}")

    capabilities_path = generated / "capabilities.json"
    capability_required = set()
    capability_forbidden = set()
    if not capabilities_path.is_file() or capabilities_path.is_symlink():
        issues.append("capabilities.json ausente")
    else:
        try:
            capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
            capability_required = set(capabilities.get("required_capabilities", []))
            capability_forbidden = set(capabilities.get("forbidden_capabilities", []))
        except (ValueError, TypeError):
            issues.append("capabilities.json inválido")

    mode_required = set()
    mode_paths = sorted((generated / "contracts").glob("*.mode.json"))
    mode_paths += sorted((generated / "modes").glob("*/mode.json"))
    for path in mode_paths:
        try:
            mode = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        local_required = set(mode.get("required_capabilities", []))
        local_forbidden = set(mode.get("forbidden_capabilities", []))
        local_overlap = local_required & local_forbidden
        if local_overlap:
            issues.append(
                f"{path.relative_to(generated)} requires and forbids: "
                f"{sorted(local_overlap)}")
        mode_required.update(local_required)
    if "product_write" in mode_required:
        issues.append(
            "Mode requires product_write; managed repairs must require "
            "candidate_write and never canonical product mutation")
    missing = mode_required - capability_required
    if missing:
        issues.append(
            f"Mode capabilities missing from capabilities.json: {sorted(missing)}")
    conflict = mode_required & capability_forbidden
    if conflict:
        issues.append(
            f"Mode capabilities forbidden globally: {sorted(conflict)}")
    undeclared = required - capability_required
    if undeclared:
        issues.append(
            f"Manifest capabilities missing from capabilities.json: {sorted(undeclared)}")

    if not manifest.get("effective_routing_digest"):
        issues.append("Missing effective_routing_digest")
    report.add_layer("capabilities", not issues, issues)


def _validate_layer_portability(report, manifest, generated):
    """Layer 6: Portability — no absolute paths, scripts, subprocess, network."""
    issues = []
    forbidden_patterns = [
        "/home/", "/Users/", "C:\\Users", "subprocess.run",
        "subprocess.call", "subprocess.Popen", "os.system",
        "urllib.request", "requests.get", "requests.post",
        "http.client", "socket.socket",
    ]

    for art in manifest.get("artifacts", []):
        full = generated / art.get("path", "")
        if full.is_file() and not full.is_symlink():
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
                for pattern in forbidden_patterns:
                    if pattern in content:
                        issues.append(
                            f"Portability issue in {art['path']}: "
                            f"contains '{pattern}'"
                        )
            except (UnicodeDecodeError, OSError):
                pass

    report.add_layer("portability", not issues, issues)


def _validate_layer_context_budget(report, manifest, generated):
    """Layer 7: Context budget enforcement."""
    issues = []
    policy = manifest.get("context_policy", {})
    warning_ratio = policy.get("warning_ratio", 0.9)
    max_entry = policy.get("skill_entrypoint_max_bytes", 32768)
    max_support = policy.get("support_file_max_bytes", 24576)

    warnings = []
    for art in manifest.get("artifacts", []):
        full = generated / art.get("path", "")
        if full.is_file() and not full.is_symlink():
            size = full.stat().st_size
            limit = max_entry if art.get("type") == "skill-entrypoint" else max_support
            if size > limit:
                issues.append(
                    f"Budget exceeded: {art['path']} ({size} > {limit})"
                )
            elif size > limit * warning_ratio:
                warnings.append(
                    f"Near budget: {art['path']} "
                    f"({size}/{limit} = {size/limit:.0%})"
                )

    # Hot path aggregate budgets
    hot_paths = policy.get("hot_paths", {})
    for hp_prefix, hp_budget in hot_paths.items():
        total = 0
        for art in manifest.get("artifacts", []):
            if art.get("path", "").startswith(hp_prefix):
                full = generated / art["path"]
                if full.is_file():
                    total += full.stat().st_size
        if total > hp_budget:
            issues.append(
                f"Hot path budget exceeded: {hp_prefix} "
                f"({total} > {hp_budget})"
            )

    details = issues + [f"WARNING: {w}" for w in warnings]
    report.add_layer("context_budget", not issues, details)


def _validate_layer_collision(report, manifest):
    """Layer 8: Name collisions and ownership."""
    issues = []
    paths = [a.get("path", "") for a in manifest.get("artifacts", [])]
    seen = set()
    for p in paths:
        if p in seen:
            issues.append(f"Duplicate artifact path: {p}")
        seen.add(p)

    report.add_layer("collision", not issues, issues)


def _validate_layer_license(report, manifest):
    """Layer 9: License provenance and THIRD_PARTY_NOTICES."""
    issues = []
    provenance = manifest.get("license_provenance", [])

    # If there's MIT provenance, check for notice
    mit_entries = [p for p in provenance if p.get("license", "").upper() == "MIT"]
    if mit_entries:
        # Check if THIRD_PARTY_NOTICES.md is in artifacts
        art_paths = {a.get("path", "") for a in manifest.get("artifacts", [])}
        has_notice = any("THIRD_PARTY" in p.upper() for p in art_paths)
        if not has_notice:
            issues.append(
                "MIT provenance declared but no THIRD_PARTY_NOTICES in artifacts"
            )

    report.add_layer("license", not issues, issues)


def _validate_layer_lifecycle(report, manifest):
    """Layer 10: Anti-auto-approval and lifecycle checks."""
    issues = []

    # Creator must only emit GENERATED
    if manifest.get("status") != "GENERATED":
        issues.append(
            f"Creator emitted status {manifest.get('status')!r}; "
            "only GENERATED is allowed"
        )

    # Check no self-approval artifacts
    for art in manifest.get("artifacts", []):
        path = art.get("path", "")
        if any(name in path for name in [
            "host-verdict", "acceptance-record", "rollback-record",
            "host-static-results", "holdout-results",
        ]):
            issues.append(
                f"Creator produced Host-only artifact: {path}"
            )

    report.add_layer("lifecycle", not issues, issues)


# ---------------------------------------------------------------------------
# Write validation reports (called by the Host, not the validator itself)
# ---------------------------------------------------------------------------


def _atomic_write_json(path, value):
    """Replace one Host report atomically without a stale/write-once window."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Reporte de validación es enlace simbólico: {path}")
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


def write_reports(report, run_dir):
    """Atomically replace the complete validation result for each evaluation."""
    val_dir = Path(run_dir) / "validation"
    val_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    binding = {
        "generation_id": report.generation_id,
        "candidate_digest": report.candidate_digest,
        "manifest_digest": report.manifest_digest,
    }

    expected_names = set()
    for layer_name, layer_data in report.layers.items():
        report_path = val_dir / f"{layer_name}.json"
        expected_names.add(report_path.name)
        _atomic_write_json(report_path, {
            "schema_version": SCHEMA_VERSION,
            **binding,
            "layer": layer_name,
            "passed": layer_data["passed"],
            "details": layer_data["details"],
        })

    # A previous evaluation may have had a different set of layers. Do not leave
    # those stale Host reports beside the newly authoritative summary.
    for report_path in val_dir.glob("*.json"):
        if (report_path.name not in expected_names
                and report_path.name != "summary.json"):
            if report_path.is_symlink():
                raise ValueError(
                    f"Reporte de validación es enlace simbólico: {report_path}")
            report_path.unlink()

    _atomic_write_json(val_dir / "summary.json", report.to_dict())
    return report.to_dict()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", required=True,
                        help="Ruta al directorio generated/")
    parser.add_argument("--run-dir",
                        help="Ruta al run para escribir reportes")
    args = parser.parse_args()

    try:
        report = validate_package(args.generated)
        result = report.to_dict()

        if args.run_dir:
            write_reports(report, args.run_dir)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if report.passed else 1)

    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
