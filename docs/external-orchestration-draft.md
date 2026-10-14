# Draft: external orchestration expansion — EARS specs, worktree kanban and local index

**Status:** RESUMED by the owner (2026-09-30) as **D11 design material**, not as the current
design. Nothing here is architecture, implementation or evidence; authority remains with
[ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) v3.0.
**Date:** 2026-09-13 (proposal) · resumed 2026-09-30
**Subordinate to:** [ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md)
(current normative design, v3.0)
**Origin:** maintainer analysis with ZCode of third-party agent tooling (Factory/droid,
Cursor, AWS Kiro, Vibe Kanban, Aider) and its fit with the existing flow.

**English** | [Español](external-orchestration-draft.es.md)

The 2026-09-30 decision does not adopt this content: it marks it as the starting point of D11
(F5 memory package, RSI and commit trigger, under "Declared debt" in
[PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md)) and sets a measurable decision condition,
the one in this draft (F5, "Exit criterion", below): a symbol-search trial measuring the cost
of navigating the repository without an index versus with one. That trial has not run, so
episodic memory remains unjustified by evidence. What the resumption does decide is that the
work is no longer parked: each increment goes through architecture, regression and
`CHANGELOG.md` like any other unit.

This document does not compete with the normative architecture or
[PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md): it proposes which third-party capabilities
are worth evaluating, which are rejected and how they would map onto the implemented pieces.
Any adoption goes through the usual rules first: maintainer decision, architecture update and
separate evidence.

## 1. Environment facts the proposal rests on

Verified 2026-09-13; re-verify at implementation time.

- **9router** operates as the Host inference layer with combos `Orquestrador`, `Subagents`,
  `ATM`, `Subagents-Audits`, `Subagents-Coding` (fallback chains across multiple providers and
  accounts, round-robin). Each client has NORMAL and RAW channels (`x-9router-token-saver:
  off`), switching RTK/Ponytail compression per request. The authorized role mapping
  (architecture §15: orchestrator and QA on RAW, execution on NORMAL) is already applied in
  the Host.
- **Alternative execution clients:** Codex CLI (v0.153.4) has combo profiles
  (`orquestrador`, `audits`, `coding` and `-raw` variants) with `wire_api="responses"`
  supported by 9router. They can run headless units (`codex exec --profile …`) without DSH.

## 2. Fit assessment by capability

| Capability | Fit | Decision |
|---|---|---|
| EARS specifications | Useful as a testable mandate artifact, not as a substitute for tests | Evaluate in F1 |
| Coding→Audits bounded loop | Useful if each pass has its own evidence and budget | Evaluate in F2 |
| Event-driven review | Useful for local diff/commit triggers; never auto-publish | Evaluate in F3 |
| Worktree kanban | Test-only parallelism; cannot be the current repair candidate, which is a Host-provisioned shadow repository with its own `.git` | Evaluate in F4 |
| Local codebase index | Only if a controlled trial measures lower navigation cost than no index | Evaluate in F5 |

## 3. Proposed phased design (draft)

### F1 — EARS specs as a mandate artifact

For a requirement that can be expressed with WHEN/THEN, emit a versioned spec before writing
code. The spec records its origin and the acceptance test that proves it; it never grants
permission to modify a repository.

### F2 — Bounded Coding→Audits validation loop

Coding makes a candidate change, Audits checks it and returns evidence. Repetition is bounded
by the mandate budget and cannot silently relax the acceptance criterion.

### F3 — Event-based review (diff → audit → external publication)

A local event can start a review but cannot publish. Publication is always a separate,
explicit operator decision; the event's digest binds the review to the diff it saw.

### F4 — Worktree kanban as a parallel execution trial

Worktrees may isolate parallel trial units only outside the canonical framework repository and
under an explicit mandate. This is a **draft experiment**, not the current repair design: the
product read-only boundary means a worktree writes into the product's `.git/worktrees/` and
fails. The implemented repair candidate is a shadow repository with its own `.git` under the
workspace.

### F5 — Local codebase index and episodic memory (local replacement for cloud indexing)

An index is warranted only if it measurably lowers the cost of locating symbols and evidence
under the same task/budget. The baseline must navigate the repository without an index; the
candidate uses a local index under the same scope. Measure time, tokens, false matches and
stale results. A useful result is a decision for D11, not permission to upload private code.

## 4. Open decisions (require maintainer decision)

- Which EARS subset is worth preserving as a mandatory artifact rather than a prompt convention?
- What is the bounded QA loop's stop rule and how is a failed pass recorded?
- What local event is an authorized review trigger, without turning it into auto-publish?
- Does a local symbol index beat navigation without one on this repository under the same task?

## 5. Non-goals (consistent with architecture §2)

No autonomous publishing, no cloud code indexing by default, no model-made Host verdicts, no
worktree inside the canonical repository for a trial, no new runtime dependency without a
measured benefit and an explicit decision.

## 6. Provenance

This is a proposal informed by the listed third-party tools and maintainer trials. It does not
copy their implementation or grant them authority. Every adopted piece needs its own
provenance, architecture change and regression.
