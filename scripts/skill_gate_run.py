"""Run the compiled corpus against real modes, or say exactly why it cannot (E3).

The gate has been able to score observations since the corpus became
executable, and nothing has ever produced one, because producing them needs a
session and a provider that the operator configures. That is a real dependency
and this module does not pretend otherwise: with no authenticated DSH it
abstains and names the missing piece, in the same words the launcher uses, so
the two answers cannot disagree.

With a session, each compiled case is dispatched to the mode under test and the
verdict is read back from what the mode persisted. The observation is bound to
the corpus, the candidate and the compiler, because an unbound verdict is what
made the legacy gate unable to tell two runs apart.

What this module never does is invent a verdict. A case the mode did not answer
is `NOT_COVERED`, and the gate abstains rather than scoring a guess.
"""

import json
from pathlib import Path

import corpus_compiler

SCHEMA_VERSION = corpus_compiler.SCHEMA_VERSION
VERDICTS = ("PASS", "FAIL", "BLOCKED", "NOT_COVERED")
MAX_EVIDENCE = 1024


class RunnerUnavailable(RuntimeError):
    """No session to run against. The message names the missing piece."""


def resolve_session(client=None):
    """The authenticated DSH client, or the concrete reason there is none."""
    if client is not None:
        return client
    import creator_client

    try:
        resolved, origin = creator_client.acquire_dsh_client()
    except Exception as error:
        raise RunnerUnavailable(
            f"no hay sesión DSH utilizable: {type(error).__name__}: {error}") from error
    if resolved is None:
        raise RunnerUnavailable(f"no hay sesión DSH utilizable: {origin}")
    return resolved


def _dispatch(client, case, mode, timeout):
    """Ask one mode to run one case and read back what it persisted.

    The evaluator prompt carries the case and nothing else: no expected
    verdict, no corpus digest, no sibling case. A case that leaked its own
    answer would measure reading.
    """
    task = case["input"]["task"]
    target = case["input"]["target"]
    request = {
        "target_mode": mode,
        "scenario": {
            "case_id": case["case_id"],
            "type": case["type"],
            "task": task,
            "fixture": case["input"].get("fixture"),
            "evaluated_claim": case["input"].get("evaluated_claim"),
            "evaluated_action": case["input"].get("evaluated_action"),
        },
    }
    response = client.rpc("evaluator", request, timeout=timeout)
    return _verdict_from(response)


def _verdict_from(response):
    """The only shapes that count. Anything else is NOT_COVERED, not a guess."""
    if not isinstance(response, dict):
        return "NOT_COVERED", "respuesta no es un objeto"
    verdict = response.get("verdict")
    evidence = response.get("evidence")
    if verdict not in VERDICTS:
        return "NOT_COVERED", f"veredicto ausente o inválido: {verdict!r}"
    if not isinstance(evidence, str) or not evidence.strip():
        return "NOT_COVERED", "observación sin evidencia"
    return verdict, evidence


def run_corpus(client, corpus, *, mode, candidate_digest, provider_name,
               timeout=900, on_case=None):
    """Every case in the corpus, bound to what produced it."""
    observations = []
    for case in corpus["cases"]:
        try:
            verdict, evidence = _dispatch(client, case, mode, timeout)
        except RunnerUnavailable:
            raise
        except Exception as error:
            # A case that could not run is NOT_COVERED with the reason, never
            # an inferred pass: the whole value of the gate is that a wrong
            # verdict is visible rather than averaged in.
            verdict, evidence = "NOT_COVERED", (
                f"{type(error).__name__}: {error}"[:MAX_EVIDENCE])
        observations.append({"case_id": case["case_id"], "verdict": verdict,
                             "evidence": evidence})
        if on_case is not None:
            on_case(case, verdict, evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": corpus["compiler_version"],
        "corpus_digest": corpus["corpus_digest"],
        "candidate_digest": candidate_digest,
        "provider": {"status": "available", "name": provider_name},
        "observations": observations,
    }


def write_observations(payload, path):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     indent=2) + "\n", encoding="utf-8")
    return path


def abstain(reason):
    """The observation set a run with no session produces: none at all.

    Not an empty list scored as zero accuracy -- an unavailable provider cannot
    claim observations, and the gate abstains instead of judging.
    """
    return {"provider": {"status": "unavailable"}, "reason": reason}
