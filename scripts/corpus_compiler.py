"""Host-owned deterministic compiler for the executable skill corpus."""

import hashlib
import json
from pathlib import Path

import acceptance_harness

SCHEMA_VERSION = 1
COMPILER_VERSION = "d11-corpus-1"
MAX_CASES = 256
SUPPORTED_TYPES = frozenset({
    "positive", "negative", "boundary", "capability-denial",
    "prompt-injection", "idempotence", "scope-violation", "write-violation",
})
VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED", "NOT_COVERED"})
ACTIONS = frozenset({"accept", "reject", "abstain"})
_HEX = frozenset("0123456789abcdef")


class CorpusError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise CorpusError(message)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_digest(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _strict_object(value, required, allowed, label):
    _require(isinstance(value, dict), f"{label} must be an object")
    _require(set(value) == set(required),
             f"{label} fields must be exactly {sorted(required)}")
    _require(not (set(value) - set(allowed)), f"{label} has unknown fields")


def _skill_names(library):
    names = {}
    for section in ("base", "catalog"):
        root = Path(library) / section
        for skill_file in sorted(root.glob("*/SKILL.md")):
            names.setdefault(skill_file.parent.name, []).append(skill_file.parent)
    return names


def _source_records(library):
    library = Path(library)
    paths = sorted(library.glob("*/**/scenarios/*.json"))
    _require(paths, f"no scenarios in {library}")
    _require(len(paths) <= MAX_CASES, f"corpus exceeds {MAX_CASES} cases")
    records = []
    ids = set()
    skills = _skill_names(library)
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CorpusError(f"invalid scenario {path}: {exc}") from exc
        required = {"schema_version", "scenario_id", "type", "description",
                    "input", "expected", "sr_links", "target_skill"}
        _require(isinstance(value, dict) and set(value) == required,
                 f"scenario has unexpected shape: {path}")
        scenario_id = value["scenario_id"]
        scenario_type = value["type"]
        target = value["target_skill"]
        _require(value["schema_version"] == 1, f"unsupported scenario schema: {path}")
        _require(isinstance(scenario_id, str) and scenario_id,
                 f"invalid scenario_id: {path}")
        _require(scenario_id not in ids, f"duplicate scenario_id: {scenario_id}")
        ids.add(scenario_id)
        _require(scenario_type in SUPPORTED_TYPES,
                 f"unknown scenario type {scenario_type!r}: {path}")
        _require(isinstance(target, str) and target, f"invalid target_skill: {path}")
        resolved = skills.get(target, [])
        _require(len(resolved) == 1,
                 f"target_skill {target!r} resolves {len(resolved)} times")
        expected = value["expected"]
        _require(isinstance(expected, dict) and expected.get("verdict") in VERDICTS,
                 f"invalid expected verdict: {path}")
        records.append((path.relative_to(library).as_posix(), value))
    return records


def validate_corpus(corpus):
    required = {"schema_version", "compiler_version", "source_digest",
                "corpus_digest", "cases"}
    _strict_object(corpus, required, required, "corpus")
    _require(corpus["schema_version"] == SCHEMA_VERSION, "wrong corpus schema_version")
    _require(corpus["compiler_version"] == COMPILER_VERSION, "wrong compiler_version")
    _require(_is_digest(corpus["source_digest"]), "invalid source_digest")
    _require(_is_digest(corpus["corpus_digest"]), "invalid corpus_digest")
    cases = corpus["cases"]
    _require(isinstance(cases, list) and 0 < len(cases) <= MAX_CASES,
             "cases must be a nonempty bounded array")
    ids = set()
    for index, case in enumerate(cases):
        fields = {"schema_version", "case_id", "type", "target_skill", "input"}
        _strict_object(case, fields, fields, f"cases[{index}]")
        _require(case["schema_version"] == SCHEMA_VERSION, "wrong case schema_version")
        _require(isinstance(case["case_id"], str) and case["case_id"], "invalid case_id")
        _require(case["case_id"] not in ids, f"duplicate case_id: {case['case_id']}")
        ids.add(case["case_id"])
        _require(case["type"] in SUPPORTED_TYPES, "unknown case type")
        _require(isinstance(case["target_skill"], str) and case["target_skill"],
                 "invalid target_skill")
        public = case["input"]
        _require(isinstance(public, dict), "case input must be an object")
        _require(isinstance(public.get("task"), str) and public["task"],
                 "case input needs task")
        _require(public.get("target") == case["target_skill"], "case target mismatch")
        _require(not ({"expected", "verdict", "oracle"} & set(public)),
                 "public case input exposes an oracle")
    identity = {key: corpus[key] for key in
                ("schema_version", "compiler_version", "source_digest", "cases")}
    _require(_digest(identity) == corpus["corpus_digest"], "corpus_digest mismatch")
    return corpus


def compile_corpus(library):
    records = _source_records(library)
    source = [{"path": path, "scenario": value} for path, value in records]
    cases = []
    for _, scenario in records:
        token = hashlib.sha256(_canonical(scenario)).hexdigest()[:16]
        cases.append({
            "schema_version": SCHEMA_VERSION,
            "case_id": scenario["scenario_id"],
            "type": scenario["type"],
            "target_skill": scenario["target_skill"],
            "input": acceptance_harness._public_input(
                scenario["type"], scenario["target_skill"], token),
        })
    identity = {"schema_version": SCHEMA_VERSION,
                "compiler_version": COMPILER_VERSION,
                "source_digest": _digest(source), "cases": cases}
    return validate_corpus(identity | {"corpus_digest": _digest(identity)})


def load_corpus(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusError(f"invalid corpus: {exc}") from exc
    return validate_corpus(value)


def write_corpus(corpus, path):
    validate_corpus(corpus)
    Path(path).write_text(json.dumps(corpus, ensure_ascii=False, sort_keys=True,
                                    indent=2) + "\n", encoding="utf-8")


def expected_verdicts(library, corpus):
    """Return Host-only oracles after proving source and compiled identities."""
    # Recompute the corpus digest from the cases actually present. Comparing the
    # declared digest field alone would accept cases edited after compilation,
    # which is the exact substitution the oracles are supposed to prevent.
    validate_corpus(corpus)
    rebuilt = compile_corpus(library)
    _require(rebuilt["source_digest"] == corpus["source_digest"] and
             rebuilt["corpus_digest"] == corpus["corpus_digest"],
             "Host source/corpus identity mismatch")
    by_id = {record["scenario_id"]: record["expected"]["verdict"]
             for _, record in _source_records(library)}
    return [by_id[case["case_id"]] for case in corpus["cases"]]


def load_bound_observations(path, corpus, candidate_digest):
    _require(_is_digest(candidate_digest), "invalid candidate digest")
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusError(f"invalid observations: {exc}") from exc
    fields = {"schema_version", "compiler_version", "corpus_digest",
              "candidate_digest", "provider", "observations"}
    _strict_object(value, fields, fields, "observations")
    _require(value["schema_version"] == SCHEMA_VERSION, "wrong observation schema_version")
    _require(value["compiler_version"] == corpus["compiler_version"],
             "observation compiler identity mismatch")
    _require(value["corpus_digest"] == corpus["corpus_digest"],
             "observation corpus identity mismatch")
    _require(value["candidate_digest"] == candidate_digest,
             "observation candidate identity mismatch")
    provider = value["provider"]
    _require(isinstance(provider, dict) and provider.get("status") in
             {"available", "unavailable"}, "invalid provider status")
    allowed_provider = {"status", "name"}
    _require(set(provider) <= allowed_provider, "provider has unknown fields")
    if provider["status"] == "available":
        _require(isinstance(provider.get("name"), str) and provider["name"],
                 "available provider needs a name")
    observations = value["observations"]
    _require(isinstance(observations, list), "observations must be an array")
    expected_ids = [case["case_id"] for case in corpus["cases"]]
    seen = {}
    for index, observation in enumerate(observations):
        item_fields = {"case_id", "verdict", "evidence"}
        _strict_object(observation, item_fields, item_fields,
                       f"observations[{index}]")
        case_id = observation["case_id"]
        _require(case_id in expected_ids, f"unknown observation case_id: {case_id}")
        _require(case_id not in seen, f"duplicate observation case_id: {case_id}")
        _require(observation["verdict"] in VERDICTS, "invalid observed verdict")
        _require(isinstance(observation["evidence"], str) and observation["evidence"],
                 "observation evidence must be nonempty")
        seen[case_id] = observation["verdict"]
    if provider["status"] == "available":
        _require(set(seen) == set(expected_ids), "observations must be complete and unique")
    else:
        _require(not observations, "unavailable provider cannot claim observations")
    return value, seen


def validate_bound_report(report, corpus_digest, candidate_digest):
    fields = {"schema_version", "compiler_version", "corpus_digest",
              "baseline_candidate_digest", "candidate_digest", "action", "reasons"}
    _strict_object(report, fields, fields, "gate report")
    _require(report["schema_version"] == SCHEMA_VERSION, "wrong report schema_version")
    _require(report["compiler_version"] == COMPILER_VERSION, "wrong report compiler identity")
    _require(report["corpus_digest"] == corpus_digest, "report corpus identity mismatch")
    _require(report["candidate_digest"] == candidate_digest,
             "report candidate identity mismatch")
    _require(_is_digest(report["baseline_candidate_digest"]),
             "invalid baseline candidate digest")
    _require(report["action"] in ACTIONS, "invalid gate action")
    _require(isinstance(report["reasons"], list) and
             all(isinstance(x, str) and x for x in report["reasons"]),
             "invalid report reasons")
    return report
