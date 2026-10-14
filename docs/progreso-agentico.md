# Improvement agentic progress — single page view · [Spanish translation](progreso-agentico.es.md)

**Updated:** 2026-10-11 (state derived from external trials, without asserting that the local modifications are integrated).

**What is this document:** a single reading of the status of **all** milestones
C/D/E/F/G/M/P/U and B0–B4, with the state derived from the cited evidence and not from the
intent. `PLAN_IMPLEMENTACION.md` is still the progress index; this file
is its joint view, so that no identifier is left to be hunted for.

**Vocabulary (taken, not invented):**

- `HECHO` — `PLAN_IMPLEMENTACION.md:17`: a proven output and gate, with recoverable evidence.
- `PARCIAL` / `DECIDIDO` / `DECLINADO` / `RETENIDO` / `PENDIENTE` / `BLOQUEADO` — vocabulary of `PLAN_IMPLEMENTACION.md:18-21`. `RETENIDO` is a preserved candidate, not accepted, and is not `DECLINADO`.
- `IMPLEMENTED_NOT_VERIFIED` / `EN CURSO` — vocabulary of `docs/status.md:4`.
- `RETIRADO` — what `docs/status.md:28-34` calls “Validity removals”.

**How to read the columns.** *Derived state* is what the cited evidence supports
today. *HUS* distinguishes milestones whose past is reused via Git (`git show`) from those that
still live in the tree.

---

## B0–B4 · Proven MVP base (pre-C0–C7 nomenclature)

| ID | What was it | Derived state | HUS | Evidence |
|---|---|---|---|---|
| B0 | Onboarding, skills, isolated Host and DSH channel | HECHO | live | `PLAN_IMPLEMENTACION.md:27`; `scripts/onboard.py`, `scripts/host_launcher.py`, `scripts/inference_channel.py` |
| B1 | Real audit, repair, QA and re-audit | HECHO | live | `PLAN_IMPLEMENTACION.md:28`; `scripts/missions.py`, `scripts/publisher.py` |
| B2 | Controller, budget, memory and metrics | HECHO | live | `PLAN_IMPLEMENTACION.md:29`; `scripts/host_controller.py`, `scripts/budget.py`, `scripts/decisions.py`, `scripts/metrics.py` |
| B3 | Write plugin and private distribution | HECHO | live | `PLAN_IMPLEMENTACION.md:30`; `tests/test_workflow_write_plugin.py` |
| B4 | Fail-closed core in two projects | HECHO | live | `PLAN_IMPLEMENTACION.md:31` |

Preserved family boundary (row B0): **not equivalent to the 3.0 onboarding flow**.

## C0–C7 Final flow stages (current in the index)

| ID | Stage | Derived state | HUS | Evidence |
|---|---|---|---|---|
| C0 | Generational contracts, library and catalog | HECHO | live | `PLAN_IMPLEMENTACION.md:37` |
| C1 | Deterministic `bootstrap install` | HECHO | live | `PLAN_IMPLEMENTACION.md:38` |
| C2 | DSH Creator automation | HECHO | live | `PLAN_IMPLEMENTACION.md:39` |
| C3 | Host validator for the generation | HECHO | live | `PLAN_IMPLEMENTACION.md:40` |
| C4 | Backups, transactional install and uninstall | HECHO | live | `PLAN_IMPLEMENTACION.md:41` |
| C5 | Automatic DSH acceptance | HECHO | live | `PLAN_IMPLEMENTACION.md:42` |
| C6 | Clean-room pilot on new projects | HECHO | live | `PLAN_IMPLEMENTACION.md:43` |
| C7 | Pilot promotion and distribution | HECHO | live | `PLAN_IMPLEMENTACION.md:44` |

**C2 needs a note its row does not carry.** On 2026-10-10 one real headless turn with the run's full `creator-prompt.md` **did not** persist `generated/generation-manifest.json`
and the run was `RETAINED`. Row C2 continues `HECHO` because its own gate was fulfilled
at the time; that pass **did not revalidate C2**. The measured cause was the lack of the overlay
in headless: without it `write` fell in the upstream queue rejected by the sandbox.
Afterwards, trial X3 did test `creator_client.dsh_headless_command` with overlay and
a real ACTIVE generation. That trial is **before** the Creator per-run budget adjustment; it does not validate a post-budget generation. See X2 and X3.

**Pointer notice:** `creator-prompt.md` does not live in the canonical tree; it is
written by `scripts/creator_client.py:1062` inside the external workspace's run dir,
so it is citable only per run, not by a repo path. The note keeps
the reference as a filename precisely so as not to point to a path
that does not exist here.
## D1–D9 · Declared debt (current in the index)

| ID | Unit | Derived state | HUS | Evidence |
|---|---|---|---|---|
| D1 | CAS/lease or atomic multi-file write of `mode-state` | HECHO 2026-10-01 (with a declared residue) | live | `PLAN_IMPLEMENTACION.md:73`; `tests/test_state_commit.py` |
| D2 | Auditor bash mechanical confinement | FACT 2026-10-01 (auditor); E4 closes the repairman | live | `PLAN_IMPLEMENTACION.md:74`; `tests/test_auditor_confinement.py` |
| D3 | `persisted_count` recount gate | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:75` |
| D4 | Notice and re-pointing on commit rewrites | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:76` |
| D5 | Candidate withdrawal as a verified mechanism | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:77`; `bootstrap.py state --retire` |
| D6 | Enum for `verification-results` | DECIDIDO 2026-09-30 (lands in E7) | live | `PLAN_IMPLEMENTACION.md:78` |
| D7 | Rich finding (fingerprint, cause, prevention) | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:79` |
| D8 | Derived view of findings closed by work item | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:80` |
| D9 | Evidence directory outside `mode-state` | HECHO 2026-09-30 | live | `PLAN_IMPLEMENTACION.md:81` |

## E1–E9 Post-C7 hardening (current in index)

| ID | Unit | Derived state | HUS | Evidence |
|---|---|---|---|---|
| E1 | Transactional commit of `mode-state` | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:85` |
| E2 | Episodic memory and index | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:86` |
| E3 | Library gate runner | HECHO MECHANISM; EXECUTION NO | live | `PLAN_IMPLEMENTACION.md:87` |
| E4 | Repairer confinement | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:88` |
| E5 | Honesty of stack coverage | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:89` |
| E6 | Close the episodic memory reading loop | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:90` |
| E7 | A genuinely calculated derived verdict | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:91` |
| E8 | The metrics ledger is read | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:92` |
| E9 | The reflection half of the RSI | HECHO 2026-10-01 | live | `PLAN_IMPLEMENTACION.md:93` |

The canonical index carries on with E10–E23, all `HECHO` in their rows. E3 keeps its
limit and it is worth not reading it as "proven": the runner's mechanism is in code and
guarded by regressions, but **there is no operational run with a real mode** because
`skill-gate-run` abstains before `session/create`, there being no Host evaluator
adapter that verifies layout and effective skill per case (`scripts/skill_gate_run.py:604-608`).
Running the corpus against your own credentials is an operator decision, not a result
of the framework.

## F1–F6 · External orchestration draft proposals (closed family)

| ID | Proposal | Derived state | HUS | Evidence |
|---|---|---|---|---|
| F1 | Specs as a versioned artifact | DECIDIDO historically: incorporate traceability, EARS optional | historical | `docs/external-orchestration-draft.md` |
| F2 | Close composition Real Host | DECIDIDO historically as core priority | historical | F2 covered by C2/C5 |
| F3 | Trigger per event and delta per push | PENDING / conditional | historical | requires remote publishing authorization |
| F4 | «1 card = 1 worktree = 1 CLI agent» | DECIDIDO historically: not to adopt | historical | `docs/external-orchestration-draft.md` |
| F5 | Three layers of life cycle | Split: layer C `HECHO` (E2); layer B `DECLINADO` 2026-10-01 | living+historical | `PLAN_IMPLEMENTACION.md:86`, `:108` |
| F6 | Specific MVP error | HECHO (B0) | live | `PLAN_IMPLEMENTACION.md:27` |

## G0–G7 · Release plan doors (closed family)

| ID | Door | Derived state | HUS | Evidence |
|---|---|---|---|---|
| G0 | License | HECHO 2026-09-30 | live | `LICENSE` |
| G1 | `recording_command` outputs the exact JSON | FACT 2026-09-29 | live | `docs/plans/10-lanzamiento-publico.md:31` |
| G2 | `decisions.py`/`metrics.py` stop being orphans | HECHO 2026-09-29 | live | `docs/plans/10-lanzamiento-publico.md:32` |
| G3 | Runtime overflow with trace | FACT 2026-09-29 | live | `docs/plans/10-lanzamiento-publico.md:33` |
| G4 | Tested off-premises clean install | FACT 2026-09-29 | live | `docs/plans/10-lanzamiento-publico.md:34` |
| G5 | Public documentation | HECHO 2026-09-30 | live | `docs/plans/10-lanzamiento-publico.md:35` |
| G6 | Tag and notes | HECHO 2026-09-30 (owner authorization) | live | `docs/plans/11-notas-beta-v0.1.0.md` |
| G7 | Verification against real stack | FACT 2026-09-29 (26 of 30 stacks without campaign) | live | `docs/plans/10-lanzamiento-publico.md:37` |
G7 keeps the limit its row requires to be published as a limit: **26 of 30 stacks
They are still declared without campaign** (`docs/status.md:250`), not as a guarantee.

## M1–M9 · MVP v2.4 core closure (RETIRADO from tree — past reused)

`docs/status.md:28-34` declares the elimination of these plans in force; `CHANGELOG.md:786`
records that commit `c8aed51` deleted the three historical documents. **No row is
current work**: reading them as backlog would invent an obligation.

| ID | What was it | Derived state | HUS | Access |
|---|---|---|---|---|
| M1 | Full queue consumption per project | RETIRADO (done in two projects) | historical | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:22-40` |
| M2 | Semantic re-audit as its own turn | RETIRADO (validated in real DSH pilot) | historical | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:41-58` |
| M3 | Real Host Controller | RETIRADO (mechanical driven cycle) | historical | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:59-76` |
| M4 | Comprehensive acceptance per project | RETIRADO (achieved with exceptions) | historical | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:77-83` |
| M5 | Decisions and instrumentation as services | RETIRADO; its two services remain at `scripts/` | live (services) | `scripts/decisions.py`, `scripts/metrics.py` |
| M6 | From “documented limit” to “proven” | RETIRADO (local portion shown) | historical | `git show c8aed51^:docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md` |
| M7 | `write` rejects the current mode | SOLVED as a plugin | live | `scripts/dsh-plugins/anti-escalation.mjs`; P5 |
| M8 | Remote distribution of the framework | Distribution RESOLVED 2026-09-13 (clean-room) | live | `docs/status.md` |
| M9 | Outline sweep over the actual bash | HECHO in its time (flag M9 inside P5) | live | P5 |

**The two documents that defined the family are only readable by Git**, and both
They carry their own “HISTORICAL CONTENT — DO NOT RUN” warning.

## P1–P11 · Hardening after C7 (current in the index)

| ID | Unit | Derived state | HUS | Evidence |
|---|---|---|---|---|
| P1 | Source Registry and Materialized Library | HECHO | live | `PLAN_IMPLEMENTACION.md:52` |
| P2 | Library integration ↔ Creator | HECHO | live | `PLAN_IMPLEMENTACION.md:53` |
| P3 | Automatic DSH dispatch and lifecycle | HECHO | live | `PLAN_IMPLEMENTACION.md:54` |
| P4 | Creator session bound to the workspace | HECHO | live | `PLAN_IMPLEMENTACION.md:55` |
| P5 | Sandbox anti-escalation policy | HECHO | live | `PLAN_IMPLEMENTACION.md:56` |
| P6 | Transaction with a Host verdict | HECHO | live | `PLAN_IMPLEMENTACION.md:57` |
| P7 | Host acceptance isolated from the Creator | HECHO | live | `PLAN_IMPLEMENTACION.md:58` |
| P8 | Mode installation as DSH presets | HECHO | live | `PLAN_IMPLEMENTACION.md:59` |
| P9 | Operational gate and real skills route | HECHO | live | `PLAN_IMPLEMENTACION.md:60` |
| P10 | Tardis pilot (Syncify) with real DSH | HECHO | live | `PLAN_IMPLEMENTACION.md:61` |
| P11 | Holdout gate for the library | IMPLEMENTED_NOT_VERIFIED | live | `docs/status.md:130` |

**P11 is the limit it serves not to soften:** the bound gate exists and decides
on verified observations, but **no library changes have gone through it
with evidence of a real agent**. The 55 cases test 25 skills, not the modes;
runner CLI stops before creating session due to missing Host evaluator
the pass abstained before `session/create`, there being no compatible Host evaluator adapter
per case. The abstention of the 2026-10-10 pass and the `NOT_COVERED` of SC-123
are evidence of two different limits, not improvement scores.

## P0–P9 · Full Architecture Execution Plan Phases (TREE REMOVAL)

**Aviso de homonimia (homonymy notice):** these `P0`–`P9` are not the eleven hardening units
above. The isolated identifier `P2` does not identify work without the document and the
era. The two documents are readable only by Git (`c8aed51`).

| ID | Phase | Derived state | HUS |
|---|---|---|---|
| P0 | Reconcile mandate, inventory and baseline | RETIRADO (executed 2026-09-13) | historical |
| P1 | Download, clean preparation and bootstrap | RETIRADO (executed) | historical |
| P2 | Host controls and real native composition | RETIRADO (executed) | historical |
| P3 | Complete audit, requirements and coverage | RETIRADO (executed) | historical |
| P4 | Complete Normal Repair and Independent QA | RETIRADO (executed) | historical |
| P5 | Reaudit, ledger and closure | RETIRADO (executed) | historical |
| P6 | Transition to final architecture | RETIRADO (executed) | historical |
| P7 | Replacement of the generic modes | RETIRADO (executed) | historical |
| P8 | Regressions and cleanup | RETIRADO (executed) | historical |
| P9 | UX, metrics, distribution and closure | RETIRADO; its public output is G5 | historical |
## U1–U6 · Workflow executor on the Host and default campaign

`U` is the only family that `PLAN_IMPLEMENTACION.md` **does not** carry as a row: its
status section lives at `docs/status.md:132-157` and its design at
`ARQUITECTURA_FLUJO_AGENTES.md:290-300`.

| ID | Unit | Derived state | HUS | Evidence |
|---|---|---|---|---|
| U1 | Plan executor without DSH | HECHO what is proven; pure Host | live | `docs/status.md:136`; `scripts/workflow.py`; `tests/test_workflow_executor.py` |
| U2 | Bootstrap entry and abstention | HECHO what is proven | live | `docs/status.md:137`; `tests/test_workflow_bootstrap.py` |
| U3 | Step `ask` with fake client | HECHO with fake client, not real DSH | live | `docs/status.md:138`; `tests/test_workflow_ask.py` |
| U4 | Distribution Bundle | PENDING · not executed (requires authorization) | live | `CHANGELOG.md:9`, `:25` |
| U5 | Skill-doctrine in `library/` | PENDING · not executed (gate with real session) | live | `ARQUITECTURA_FLUJO_AGENTES.md:294` |
| U6 | Defect audit and repair campaign | IMPLEMENTED_NOT_VERIFIED · without operational acceptance | live | `docs/status.md:4`, `:142`, `:156` |

**U6 has moved somewhat, and it matters to be exact.** On 2026-10-10 the workflow
showed, with real DSH, `FAIL → reparación → PASS` in two separate and verified runs
(`r-5d7d11…` `RETAINED cause: gate-abort:gate-producto`; `r-7761c0…` `COMPLETED`), and
fail-closed memory invalidation (`MEMORY_RECONCILED`, 6 invalidated). That
exercises the mechanism, **not** operational acceptance: the product was fictitious and the
campaign does not close out the rules for a real repository.

## X1–X3 · Evidence after the 2026-10-10 pass

| ID | Unit | Derived state | Evidence and limit |
|---|---|---|---|
| X1 | Repair candidate without `worktree` of the product | REAL HOST/SHADOW AND PRESET TESTED; entire cycle EXERCISED IN TWO TURNS | In `x1-live`, a fictional product and headless DSH exercised Host provision out of mode, `PROVISIONED → DIRTY`, diff verified, tests 3/3 and exact resume; The product was left intact. The corrected `bwrap` wrapper denied writes to the product, but headless did not compose the preset (0 calls to `skill`) and two turns totalled 386,441 tokens versus 250k. In `x1-preset-real`, DSH web resolved the actual preset and loaded its skill, with a read-only boundary around the Host shadow; with a ceiling of 120,000, the supervisor stopped the execution **before editing** due to a prediction of exceeding it (104,372 measured, 129,898 projected; in a later round 97,973 measured, 127,227 projected). **With a ceiling of 200,000, it did manage to edit**: 11 steps and 180,107 billable tokens, the shadow was left dirty with the canonical defect repaired (`Math.round(valor)` → `Math.round(valor * 100) / 100`, and the VAT-inclusive total rounded over an already rounded rate), the tests (3/3, executed by the operator from outside) passed against the shadow and the canonical product was left intact; the turn stopped on projection (180,107 measured, 208,828 projected) before the second dirty claim and the closure `DIRTY`. The final stretch was closed in a later turn, with the commands published as files verified by digest: the mode recorded `DIRTY` with digest and paths, persisted `work-items.json` and executed the entrypoint (3/3). The two stretches of the cycle were exercised, in separate turns. External tests: `x1-live/RESULTADO.md` and `x1-preset-real/RESULTADO.md` |
| X2 | Web server and evaluation transport | BOOT PROVEN; HOST EVALUATOR ABSENT | `dsh web` did boot on `0.2.0-rc.2`; the failure of the previous pass was the copied home with empty `profiles/web/node_modules/`, not a current blocker of the starter. **There is no** `evaluator` endpoint in that version: the gate uses the actual sessions API (`session/create` + `session/prompt` + `session/page`), but the CLI does not have a supported Host evaluator adapter that checks the per-case `cwd` and the effective skill before creating the session (`scripts/skill_gate_run.py:604-608`). This is distinct from the Creator generating or the corpus targeting |
| X3 | Creator and corpus gate against a real mode | PRE-BUDGET CREATOR ACTIVE; CORPUS NOT_COVERED | With a model-facing headless overlay, Creator generated a manifest `GENERATED` with 19 artifacts and `bootstrap accept`, and the Host activated it `ACTIVE` (external test `ensayo-x3-actualizado.md`). **This ran before the Creator budget fix**; it does not accredit post-budget generation. At `corpus-fixed`, the corrected frontmatter allowed `skills/list` with 4 real skills `modelInvocable` and `skill`, and one of the 55 cases (`SC-123`) was dispatched. The gate gave `NOT_COVERED`: the compiled case pointed to the **skill** `source-driven-development`, not the mode `fixture-auditor` that was shipped, and the mode required a CWD layout (`ensayo-x3/fixture/workspace`) that the gate did not give it (it ran at `case-workspaces/SC-123`), so `__IMPROVEMENT_LAYOUT_OK__` was never emitted, the mode narrated `RETAINED` without `workflow_write` and `result.json` was never written. The gate did not invent PASS. External tests: `corpus-fixed/RESULTADO.md`, `x3-corpus-live/RESULTADO.md` |

## How to get to the evidence

- Current status and the real pass's footprints: [status.md](status.md)
- Progress and debt index: [../PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md)
- Normative design: [../ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md)
- Change history: [../CHANGELOG.md](../CHANGELOG.md)
- Verified procedure for a real DSH session: [../skills/dsh-maintenance-session/SKILL.md](../skills/dsh-maintenance-session/SKILL.md)

Nothing in this document turns a static regression into live testing: every row
`HECHO` is so because of its gate, and every row that is not `HECHO` names the missing piece.