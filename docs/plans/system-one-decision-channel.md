# Design: System 1 decision-model channel as an advisory proposal

**Status:** design approved for phased implementation. No phase is implemented yet except Phase 0,
which is already in the tree.

**English** | [Español](system-one-decision-channel.es.md)

**What it is and is not.** A *decision model* (System 1) is not a cheap LLM or a fast mode of the
model we already use: it is a different architecture. It generates no text. It takes a `state`
(text or JSON), a list of allowed options and a rubric, and returns a probability distribution
across those options. The example that launched the category is **Jev** from TypeSafe AI
(announced 2026-09-16, https://typesafe.ai/blog/introducing-system-one-models-and-jev),
trained with *RL for Calibrated Decisions*. The architectural reference is Talker-Reasoner
(arXiv 2410.08328): System 1 **proposes** and System 2 **endorses or vetoes**.

## The rule governing the whole design

> A System 1 in this framework **expands coverage and never grants authority**.

This is not a preference: it is the same rule that already governs `skill_router`
(`authorizes_execution: false` always, `scripts/skill_router.py:192`) and the reasoning level
(which never grants a verdict or a capability). A decision model produces a **proposal with a
rubric digest**; the Host verifies it, records it and may revoke it. If the proposal cannot be
verified, it is discarded.

## Evidence motivating the channel (measured, not vendor claims)

| Source | Result |
|---|---|
| Vals AI (independent, https://www.vals.ai/blogs/independent-evaluation-of-jev) | Claim verification **0.975**, tying GPT-6 Astra at **1/498 the cost** ($0.02 vs $12 per 1,000 cases); 194× lower latency in batches of 32. **ECE calibration 0.011**, best of 12 systems. |
| arXiv 2610.11978 (13 benchmarks, 19 LLMs) | Wins on knowledge (MMLU-Redux, ARC-Challenge) but **17.7 points below the median in math** and below all 19 compared models. |
| Vals AI, LegalBench | **Last of 12** (0.730) and calibration **0.108**, worst of the set. |
| Vendor, https://docs.typesafe.ai/model-jaggedness/jev-1.13 | "If you give it a hard target it will compress the ambiguity into a choice, even if the choice is wrong"; "cannot reason over long chains of steps"; 16k context; "should not be used for decisions requiring human oversight". |

**The conclusion that decides the design:** calibration measured on one task **does not
transfer** to another (0.011 for claims, 0.108 for legal). The dangerous failure mode is not a
visible error but a **high-confidence wrong choice**. That is why the channel is designed so a
System 1 failure is **cheap and detectable**, never silent.

## Phases

**Phase 0 — transport unblock (implemented, commit `4352a55`).**
`DshLocalClient` wraps `session/selectModel` and `session/projections`
(`scripts/creator_client.py`). Without this, even System 2 could not apply a per-step reasoning
level, so System 1 would have been integrated into a client unable to select a session. The
level is validated before the wire and a response whose `applied` does not match raises rather
than pretending it was applied.

**Phase 1 — versioned rubric (prerequisite; no channel without it).**
The result depends on the rubric, so the rubric is a **versioned input with a digest**, not a
string hidden in code. It is validated like any other framework artifact. Without a rubric
digest, a proposal is not auditable: there is no proof of the criterion that produced it.

**Phase 2 — the advisory channel (pilot: finding deduplication).**
`episodes.signature` (`scripts/episodes.py:51`) identifies a defect by `(path, excerpt)` or a
fingerprint. The exact key misses duplicates described in different words. The channel adds:
given a new finding and existing ones, a `choice` over "same defect?" with a confidence
threshold. Below it: a **named abstention**, not a guess. The existing evidence digest forces
human auditor review, so a misclassified duplicate is visible.

**Phase 3 — candidate facts for the router.**
`skill_router` aborts with `ambiguous_observations` when two observations of the same fact
disagree (`scripts/skill_router.py:118-121`). The channel may propose facts from free text; the
Host **still requires** each fact's `evidence_sha256`. This bounds coverage, not replaces
validation.

**Phase 4 — cycle failure classification (diagnostic).**
Real case from this session: a turn died with `zlib.error: incorrect data check` of unclear
cause. A `choice` among "decode error, identity error or layout error?" speeds up diagnosis.
It only labels the failure: it neither repairs nor evaluates it.

## Test and compilation orchestration: proposal, not execution

A System 1 decision model cannot execute `npm test`, `cargo check`, a build, a compiler, or any
other tool: it returns a choice or probability, not a process result. Its useful role would be
**ordering** an already authorized set of checks, for example "fast unit tests first, then the
required full suite" or "run the TypeScript compiler before browser checks", based on a bounded
state (`changed_paths`, stack/capability plan, historical runtimes). The Host supplies the allowed
options, enforces the capability plan and executes commands; the actual exit code, coverage,
stdout/stderr and candidate digest remain the evidence. A low-confidence or out-of-distribution
choice abstains and follows the deterministic plan. It must never suppress a mandatory check,
turn a failed compilation into `PASS`, invent a tool entrypoint, or treat the model's confidence
as evidence that a command ran. Whether this improves mean latency/cost without reducing defect
recall is **unmeasured**; compare on real project changes and count all escalations.

This is a candidate research seam, **not a new mode** and not an implementation commitment.

## Where it must NOT enter, and why

Verdicts, acceptance, diff verification, reconciliation and candidate adoption. There,
"ambiguity compressed into a wrong choice" is a silent failure, not a visible error. Those are
exactly the points where the framework deliberately fails closed today.

## Cascading pattern that translates directly

Measured by Vals AI: forwarding 1% of cases to a frontier model costs 27 cents per thousand.
The translation is: **declared threshold as policy, forwarding as execution**. System 1
classifies; below threshold it escalates to the expensive model or the operator. The threshold
is plan data, not a hidden constant.

## Verification required before claiming anything

1. Measure precision and calibration **on our own distribution**, not public benchmarks. If
   calibration does not hold, the answer is no.
2. No test may claim that the model decided: only that it proposed, and with which rubric digest.
3. The pilot (Phase 2) runs with an injected fake client/server, like the rest of the tree; the
   real run against Jev is a separate step and remains unexercised until it happens.

## Ideas the channel opens (not committed)

- **Budgeted forwarding:** how many cases get forwarded is a measurable cost policy, not a
  judgment.
- **Two sizes (`min`/`pro`) by campaign stage**, like reasoning effort by stage today.
- **Loop detection:** if the same defect returns after N approaches, the channel stops
  classifying: the ledger marks it (`MAX_PER_SIGNATURE = 3`, `scripts/episodes.py`).
