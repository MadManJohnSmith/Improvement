# Implementation plan and progress · [Español](PLAN_IMPLEMENTACION.es.md)

**Status:** C0–C7, P1–P11 and pilot hardening units retain verification with recoverable evidence; The open work is in “Declared debt”, in gates G0–G6 of the [launch plan](docs/plans/10-lanzamiento-publico.md) and in the debt X1–X3 that opened the pass on real DSH of 2026-10-10.
**Update:** 2026-10-10
**Architectural source:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md) v3.0

This file is the only progress index. It preserves three levels:

1. **Proven MVP Foundation:** Already demonstrated capabilities with real DSH, Syncify and RehabWeb.
2. **C0–C7:** implementation of the final flow of a command: bootstrap → automatic Creator → specific modes/skills → Host validation/backup/acceptance → activation/rollback. Completed.
3. **Post-C7:** hardening of the flow on real evidence of pilots in progress.

Historical details are at `CHANGELOG.md`; private evidence, candidates, sessions and logs remain outside the repository. No document or generated state certifies execution by itself.

## States

- `HECHO`: output and gate checked with recoverable evidence.
- `PARCIAL`: mechanism or limited test; part of the gate is missing.
- `PENDIENTE`: not implemented or without sufficient evidence.
- `BLOQUEADO`: requires decision, permission or external capacity.
- `RETENIDO`: candidate preserved, but not accepted.

## Proven MVP foundation

| ID | Outcome | Status | Main evidence | Kept limit |
|---|---|---|---|---|
| B0 | Onboarding, skills, isolated Host and DSH channel | HECHO | `scripts/onboard.py`, `host_launcher.py`, `inference_channel.py`, fixture presets, tests; `docs/status.md` | It is not equivalent to the Creator 3.0 bootstrap |
| B1 | Real audit, repair, QA and re-audit | HECHO | Syncify/RehabWeb cycles; `missions.py`, `publisher.py`; branches `workflow-repairs` | `RETAINED` product units are not presented as repaired |
| B2 | Controller, budget, memory and metrics | HECHO | `host_controller.py`, `budget.py`, `decisions.py`, `metrics.py` and regressions | Remote descendants/physical power loss remain limited |
| B3 | Plugin for private network writing and distribution | HECHO | `workflow-write`, remote clean-room, regressions | The plugin needs portable packaging in C4 |
| B4 | Fail-closed core MVP in two projects | HECHO | 17/17 stateful units, restorable files, `docs/status.md` | It accepts the framework, it does not declare products free of defects |

## Current stages C0–C7

| ID | Output outcome | Status | Main work | Exit gate |
|---|---|---|---|---|
| C0 | Generation contracts, library and catalog | HECHO | Schemas for run/manifest/project/capabilities/modes/skills/tests/handoffs/drift; immutable base library; catalog of specialized patterns; valid/invalid fixtures; MIT provenance | The validator processes the positive/negative corpus and shows that Creator selects base/catalog before proposing extensions |
| C1 | `bootstrap install` deterministic | HECHO | DSH/provider/Creator preflight; workspace; generation-id; snapshot/authority; general skills; Creator prompt/package; checkpoint/resumption | A clean clone prepares a full run without modifying product/global config |
| C2 | DSH Creator automation | HECHO | A real DSH Creator session with cordis preset was run; it generated a complete project-specific package and ran bootstrap.py accept | One command generates a valid project-specific package and demonstrates why it does not use the reuse layers before generating an extension |
| C3 | Host generation validator | HECHO | An independent 10-layer validator was run over the real C2 package; verdict READY_FOR_ACCEPTANCE | The negative corpus fails closed before any backup/active write |
| C4 | Backups, transactional installation and uninstall | HECHO | Verified backup, staging, atomic swap and rollback verified over the real package | Injected failures never leave a mixed set; the previous state is restorable |
| C5 | Automatic DSH acceptance | HECHO | Creator invoked accept; the Host ran static validation, an evidence ledger and a fail-closed verdict | Creator invokes `accept`; only the Host emits ACTIVE or RETAINED/rollback |
| C6 | Clean-room pilot in new projects | HECHO | Clean-room pilots run on a Python/backend project and a multipart project (Python+TS) with real DSH, metrics, rollback and uninstall | A user with DSH/provider configured gets specific modes with one command |
| C7 | Pilot promotion and distribution | HECHO | Run reconciliation executed; THIRD_PARTY_NOTICES.md (MIT) added; preparation and publication verified | Linkable repo for testers, pinned version and repeatable clean-room |

## Post-C7 — hardening on real pilot

Units after C7, each with a flow change, a regression and an entry in `CHANGELOG.md`:

| ID | Outcome | Status | Verified content |
|---|---|---|---|
| P1 | Source registry and materialized library | HECHO | 50 sources with fixed provenance (commit or `spec_version`); 21 immutable base skills and 4 catalog patterns with activation criteria and scenarios; bidirectional regression |
| P2 | Library ↔ Creator integration | HECHO | Library snapshot per run, prompt with base/catalog, `reuse_reference` resolved by the Host validator against the snapshot |
| P3 | Automatic DSH dispatch and lifecycle | HECHO | Stopping of previous instances, port ownership, HMAC home cookie, non-interactive launch with diagnostics, usable provider resolver |
| P4 | Creator session bound to the workspace | HECHO | `workspace/create` + `workspaceId`; a single Creator session, grouped in the UI, with no evaluator/reviewer sessions or delegation; `workspace-write` boundary = the run workspace |
| P5 | Anti-escalation sandbox policy | HECHO | Framework plugin: escalation fields out of the tool schemas, bash escalation kept, same mode corrected in `workflow_write` (overlay `dsh web --patch`); the prompt forbids the whole channel |
| P6 | Transaction with Host verdict | HECHO | `install` requires an explicit `ACTIVE` verdict from the same generation before activating |
| P7 | Host acceptance isolated from Creator | HECHO | Host harness with isolated evaluator and reviewer, hidden cases with private predicates, full cardinality, actors correlated with real DSH turns |
| P8 | Mode installation as DSH presets | HECHO | `@deepseek-ai/dsh-agent-preset` declaration bundle installed by `pluginManager/installBundle`, with the roster verified via `agentPresets/list`; deterministic `READY_FOR_INSTALL` before `ACTIVE` |
| P9 | Operational gate and real skill path | HECHO | Every mode requires persona+bash+fs+fs-search (`sampleOverCapGlobResults: false`)+skill-filesystem+tool-skill and rejects delegation/workflow/web/plugin-manager; minimum frontmatter validated; the bundle copies skills/resources and mode skills, with an exclusive local root and a receipt for both presets |
| P10 | tardis pilot (Syncify) with real DSH | HECHO | 77 distinct findings (114 records) attended by the modes with handoff and verification; integration only by operator commit/fast-forward/push and green CI on 3 jobs in `b9413eb`. The closing record declares D-01..D-04 as conditional scope (SoundCloud/Apple Music depend on owner credentials), not as pending work |
| P11 | Durable handoff and bounded repair | HECHO | Exact skill bootstrap, schemas/caps, preflight migration by digest, deterministic candidate recorded before the first change, no implicit commit, and canonical invariants, with regressions. Exercised with real DSH in three later campaigns (RehabWeb, LoboApp and the framework self-test). Two limits remain unimplemented and are declared debt, not part of this unit: the mechanical confinement of bash and the multi-file CAS/lease |

Current regression suite: see the latest record in `CHANGELOG.md`; the full suite runs green before every unit closure.

## Declared debt

Open work with evidence behind it, not on paper. Each line is a unit
pending with its closing criterion; none are implied by another `HECHO` state.

| ID | What's missing | Status | Closing |
|---|---|---|---|
| D1 | CAS/lease or multi-file atomic write by `mode-state` | HECHO 2026-10-01 | Lease per file with 30 s TTL: closes concurrent replacement of the same file. The atomicity of the batch of five files is **not** closed—the backend does not offer a transaction—and is still declared in `write_method` |
| D2 | Auditor bash mechanical confinement | HECHO 2026-10-01 | **Measured against installed `0.1.7-rc.2`, not inferred.** `dsh-sandbox-policy` resolves `workspaceRoot` from the session cwd, and that's the error: the writable root was the **parent** of the product and the workspace, so `workspace-write` allowed the product to be clobbered by both bash and `ctx.fs` (verified: product content passes to `CLOBBERED`). **Pointing the policy to the workspace instead of the session root resolves this**: the product is left out of `writableRoots()`, bash receives the actual `EROFS` ("Read-only file system"), descendants inherit the border, and auditor state writes **continue to work** — both by bash and `ctx.fs.writeText`. The previous premise was true in its fact and false in its conclusion: `read-only` does deny any mutation of `ctx.fs` (proven), but `read-only` is not necessary; `workspace-write` on a narrower root gives what was sought without denying the state. **The fixer is still blocked, and for a reason that had not been isolated:** `writableRoots()` supports **a single** configurable root (`dsh-sandbox/lib/index.js`), and the fixer needs two — its candidate and the shared state. Skimming the candidate's policy leaves the product read-only but denies `mode-state`; and `git worktree add` registers the worktree in the `.git` **of the product**, which is now read-only, so a confined session cannot provision its own candidate (`git_exit=255`). Closing it requires the Host to provision the candidate outside the confined session, not a policy patch. All of this is set to `tests/test_auditor_confinement.py` against the real runtime, with negatives: root in session = 5 tests fail, `read-only` = 2 fail |
| D3 | `persisted_count` counting gate against the file | HECHO 2026-09-30 | central `count_command` that recalculates the open set from the file and prints the number; the handoff must cover exactly that set and `workflow_write` rejects it if not |
| D4 | Assisted warning and re-targeting when rewriting commits after integrating | HECHO 2026-09-30 | `bootstrap.py state` detects it (`integrated_head_rewritten`) and `--repoint` only accepts ancestor review of the canonical HEAD with clean product, with receipt in `overflows.jsonl` |
| D5 | Withdrawal of candidate as a verified mechanism, not procedure | HECHO 2026-09-30 | `bootstrap.py state --retire` checks condition by condition and is idempotent; the manual procedure of `docs/usage.md` remains as an explanation, not as a step |
| D6 | `verification-results` enum: `PARTIAL` enter or require closed enum with justified N/A | DECIDIDO 2026-09-30 | The enum remains closed and `PARTIAL` becomes a verdict **derived** by finding (worst result wins: FAIL > BLOCKED > PASS), with one record per entrypoint; `REPAIRED` does not enter |
| D7 | Rich finding (fingerprint, cause, recurrence prevention) in `mode-state` | HECHO 2026-09-30 | `evidence.path`+`excerpt` with `line`, `located` and `fingerprint` calculated by the tool; `cause` and `prevention` bounded to 256 B and the 4.096 B cap of the register checked at the write limit; cast `anchors` into `bootstrap.py state`. The three new fields are optional, so historical evidence is not archived |
| D8 | Derived view of findings closed by work item VERIFIED | HECHO 2026-09-30 | `bootstrap.py state` names `closed_findings` and `uncovered_findings` without rewriting the ledger |
| D9 | Evidence directory outside of `mode-state` for patches and large logs | HECHO 2026-09-30 | Managed root `<workspace>/evidence` with own limits (8 MiB/file, 256 MiB, 200 files, safe name) and receipt in `overflows.jsonl` upon discard; `workflow_write` accepts it and continues to deny everything else |
| D10 | Template that distinguishes full audit from incremental (anti-anchoring) | HECHO 2026-09-30 | `audit_scope` in the contract and the person: in a full audit the queue is observed before being read, in an incremental one it starts from the diagnosis; the scope travels in the `handoff_id` and `bootstrap.py state` counts both |
| D11 | F5 memory package, RSI and commit trigger | HECHO 2026-10-01 | **The mechanism is now executable; execution is still missing.** `scripts/corpus_compiler.py` compiles the 55 `library/` scenarios into deterministic executable cases (`task` + fixture + `evaluated_claim`, reusing `acceptance_harness._public_input`), linked by `source_digest` and `corpus_digest`; `bootstrap.py compile-corpus` produces it and `bootstrap.py bound-skill-gate` scores against it. **The oracle does not travel in the public case**: `expected_verdicts` is derived on the Host and only accepts a corpus whose recalculated digest matches the declared one — a corpus edited after compiling is rejected, and that check was added by a regression that found the gap. Observations are tied to corpus, candidate, and compiler version, and cannot be declared by a `unavailable` provider. `bootstrap.py skill-gate-commit-check` requires a bound and accepted report when they change `library/` or the gate itself, and **abstain blocks the same as reject**: abstention is not permission. The four gate decisions are exercised against the real corpus (accept, reject for not improving, reject for regression in training, abstain) with 27 regressions, each one tested by breaking what it protects. **What's still open and why:** No library changes have yet passed through the gate with observations from a real agent, because running the corpus requires a provider configured by the operator — the framework does not install or invoke it. The commit trigger exists as an explicit command for a hook or CI, not installed as a hook. F5 (episodic memory and index) is E2 and is closed; what remains open is its execution, not its design |
| D12 | Beta publication (tag and push) | HECHO 2026-09-30 | G6 closed with authorization of the owner: tag `v0.1.0-beta` and `dev` published; notes in `docs/plans/11-notas-beta-v0.1.0.md` |
| E1 | `mode-state` transactional commit (D1 closed) | HECHO 2026-10-01 | A write-ahead marker in `mode-state/.commit.json` names the unit and each (path, digest) pair that is to land; the marker is cleared when the unit is closed, and if it appears dangling the startup reconciliation declares the unit RETAINED, naming which files were left. **Own decision:** True multi-file atomicity is impossible without a single-file store, and the alternative to detecting it—ignoring it—is what silently produces inconsistent state. Detection and recovery is purchased, and it is declared that it is not atomicity |
| E2 | Episodic memory and index (F5 closed) | HECHO 2026-10-01 | `mode-state/episodes.jsonl` with one record per closed unit — defect signature, class, fix that worked and verification that tested it - plus `mode-state/episodes-index.json` that maps signature to ids for O(1) query without loading the log. Only the Host writes the log; The mode reads it and **has to consult it before persisting a finding**, marking the repetitions with the previous episode. **Own decision:** without this the auditor re-reports the same defect each session, which is the most expensive memory failure that this framework has |
| E3 | Library Gate Executor (D11 closed in code) | HECHO 2026-10-01 (mechanism; execution without evidence) | `bootstrap.py skill-gate-run` **checked mechanism in code**: dispatches each compiled case against the real mode through the Host session API and writes observations bound to corpus, candidate and compiler version, confining traversal and symlinks, reusing already read `result.json`, and closing the oracle output and the case's `type` tag. **The operational execution is NOT done:** the runner requires a compatible Host evaluator adapter that verifies before `session/create` the compatible layout per case and the effective availability of each target skill; the CLI doesn't offer it, so today the answer is `ABSTAINED` for good reason. The regressions that demonstrate this (1075 OK, 11 skips without external runtime) cover manufactured rejection and abstain, not a run with real mode. **Own decision:** The run with real agent credentials is the operator's and cannot be manufactured; the path to it is framework code and already exists, but anyone who claims that E3 is operationally tested is confusing mechanism with execution |
| E4 | Repairer Confinement (D2 closed) | HECHO 2026-10-01 | The candidate stops being a *worktree* of the product and becomes an **autonomous shadow repository** with its own `.git`, created by the Host within the workspace. **Own decision, and it is measured:** a worktree stores index and HEAD in the `.git/worktrees/` of the product, so a product with read-only `.git` makes `git add`/`git status` unusable in the candidate — confinement and worktree are incompatible. With shadow repo, a single writable root covers candidate and state, and the product remains true read-only. The integration becomes the diff that the operator applies |
| E5 | Stack Hedging Honesty | HECHO 2026-10-01 | For the seven stacks declared but not tested in a real campaign (Node, Go, Maven, Gradle, .NET, PHP, Ruby), a regression checks that the declared verification command **resolves** against a minimum fixture of that technology, and the documentation says per stack if there is evidence of a real campaign or just a declaration. **Own decision:** a plausible handwritten command is not coverage, and the difference has to be visible to whoever uses the beta |
| E6 | Close the episodic memory reading loop | HECHO 2026-10-01 | The closing audit found that E2 wrote `episodes.jsonl` and `episodes-index.json` but no product path read the index: the documentation said "the auditor consults it" and the framework reported the same defect again. `workflow_write` now consults the exact signature that `evidence.prior_episode` calculated and stamped when an already verified fix had closed that code; a mode cannot self-declare it, a present but unreadable index fails closed and an absent index means empty memory. `bootstrap.py state` makes the failed prevention visible in `repeats`. One regression runs eight cases and was canary-checked by deleting the query; another binds persona, contract and plugin so they do not diverge again |
| E7 | The derived verdict is promised in three places and was not calculated in any | HECHO 2026-10-01 | The plugin kept one record per entrypoint and said in its own comment that "the Host derives it"; the contract declared `worst-result-per-finding-and-candidate-partial-is-derived-not-written` and the person told it to the mode. `stack.derived_verdicts` existed, was regressed, and was not called by anyone outside of `tests/`: a partially verified finding had no verdict anywhere. Now `state` derives it in reading and adds `partial`, which gave the naked verdict: `BLOCKED` with a PASS and a BLOCKED is progress, `BLOCKED` with a single BLOCKED is not having run at all |
| E8 | The metrics ledger was written and no one read it | HECHO 2026-10-01 | The controller logs a `turn` event per unit closed; `metrics.summarize` and `metrics.verify` had six regressions and no calls. `bootstrap.py metrics --mission` checks the string **before** adding it—a total on a manipulated ledger is not a measurement—and declares `NO_DISPONIBLE` the unrecorded, never zero, because zero would claim that the mission cost nothing |
| E9 | Half RSI reflection | HECHO 2026-10-01 | The gate rejected, printed the reason and threw it away: the next attempt started from scratch and paid an entire agent run to receive the same response. `scripts/reflection.py` saves the rejection with its holdout before and after, `bound-skill-gate --buffer` records it, **resubmitting an already rejected candidate against the same corpus rejects it without scoring it**, and `skill-gate-reflect` gives the summary that the next attempt should read. A rejection of another corpus does not apply: answered another question |
| E10 | Stack coverage was not falsifiable | HECHO 2026-10-01 | Two `docs/status.md` tests only checked that four strings appeared near a header, with the tested set hardcoded in the body of the test: **editing the document to claim a campaign that never happened left them green**, and a new stack in the log did not have to appear in the table. `stack.CAMPAIGN_EVIDENCE` declares the evidence alongside the commands and the tests now require both directions — tested with its campaign, declared without it. Canary: faking Go in the document breaks the suite |
| E11 | The account that is published did not say what was not executed | HECHO 2026-10-01 | “NNN tests in green” simply covers eleven regressions that do not run without `DSH_MODULE_ROOT`, `node`, `bubblewrap` or `jsonschema`. `docs/status.md` names each component and what is lost with it, and a regression checks that **no `skipTest` in the repo can exist without naming a component that the repository does not distribute** |
| E12 | Commands that worked and no one could find | HECHO 2026-10-01 | `audit.py archive`, `missions.py reaudit`, `transaction.py install\|rollback\|uninstall` and `skill-gate-run` were not in `docs/usage.md`. Documented as a service surface, with `metrics` and `skill-gate-reflect`. The regression loops through the repo's `add_parser`, so a new undocumented subcommand fails there |
| E13 | The issued contract was not validated against its schema | HECHO 2026-10-01 | The budget test built the `mode.json` document to measure bytes and that was it. It is now validated against `schemas/modes.schema.json` with `generation_contracts.validate("mode-contract", …)` for both roles, and the check is tested non-empty with a `candidate_root` which the schema prohibits — the exact drift that broke acceptance when `candidate_location` became out of sync |
| E14 | Orphan code and duplicate readers | HECHO 2026-10-01 | AST analysis on `scripts/`: `stack.derived_verdicts`, `stack.validate_verification_results`, `stack.allowed_verification_commands`, `metrics.summarize`, `metrics.verify`, `episodes.stats` and `episodes.read_episodes` were not called by any product path. All seven are wired. `episodes.is_repeat` is **removed**: with E6 the reader is the plugin, and a second reader without callers is a second source of truth |
| E15 | The only real declaration from the repository was outside the invariant that the suite tests | HECHO 2026-10-01 | `test_stack_coverage` demonstrates that “plan ready ⇒ executable command” for eleven synthetic products, and the `improvement-verification.json` of the framework itself—the only statement published—was not resolved by any test. `stack.declared()` validates form, not execution, so a truncated command would still resolve to `verification_ready: true`. Now the test resolves the repository's plan and launches its command: both going green and continuing running after ten seconds are worth it, and dying in the argv is not worth it. Canary: the same command without its last argument |
| E16 | No schema said who applied it | HECHO 2026-10-01 | Nineteen of twenty-two were reachable through the `generation_contracts` registration; The three contracts of the corpus were applied by a hand-made validator in `corpus_compiler` to which nothing pointed, and two of the others were addressed with a name that was not the name of their file (`mode-contract` for `modes.schema.json`). `SCHEMA_VALIDATORS` declares the union in the product, `schema_enforcement()` resolves it, and `validate()` supports both spellings; the regression requires exact bijection with `schemas/`. Canary: a loose schema breaks the suite |
| E17 | The suite account was kept by hand | HECHO 2026-10-01 | "743" and "755" to sixteen lines in the README, without saying which one was current. The count is now discovered with `TestLoader().discover(...)`, and a mismatched figure has to be declared again at that point. Canary: 760 → 799 in the README |
| E18 | Nobody read the golden fixtures | HECHO 2026-10-01 | `fixtures/README.md` claims that its golden manifests validate generators and validators and carry no paths or credentials; nothing opened `fixtures/`. The four manifests are now validated against `generation-manifest` and `project-manifest` on every run, with non-emptiness (removing a required field makes them fail), and the sanitization and no-install rules are mechanical |
| E19 | The skills installer was silently losing skills | HECHO 2026-10-01 | `prepare_project_skills` selected directories for having a `SKILL.md` and copied without parsing: unreadable frontmatter or a different directory name was installed and nobody found out, and a directory with content but no `SKILL.md` was lost without appearing in the result — which the architecture forbids in preflight. Now it fails closed naming the directory and validates the frontmatter; an empty directory is passed through. The five real skills validate themselves. The earlier test used a skill with literal line breaks that passed only because nobody read it |
| E20 | The attribution was one step away from public notice | HECHO 2026-10-01 | Each of the 25 skills states in its `## Procedencia` which upstream it was adapted from, and `test_attribution_present` was satisfied with the word "MIT". `THIRD_PARTY_NOTICES.md` named a single upstream while `docs/status.md` claimed that the MIT attribution of `obra/superpowers` and `addyosmani/agent-skills` was already done. The two upstreams, with their fixed revision, license, and MIT text, are now in the notice, and the regression requires upstream **and** revision for everything the library declares. Canario: cut the review in the notice breaks the suite |
| E21 | Nobody verified the canonical tree rule | HECHO 2026-10-01 | `AGENTS.md` requires runtime artifacts to live outside the repository and says that ignoring them in Git is not enough; there was only `.gitignore`. `tests/test_canonical_tree_holds_no_run_artifacts.py` fails by name against any run file or directory within the tree, with the vocabulary taken from the `scripts/` literals — and a second test rereads those literals and requires the inventory to cover them, which is how `evidence-ledger.jsonl` and `scenarios.jsonl` appeared in the first run. `fixtures/` is exempt by design and subject to its own sanitation rule. Canary: planting `mode-state/work-items.json` |
| E22 | Two guardrails that AGENTS.md requested and no one had installed | HECHO 2026-10-01 | The "no maintainer local routes" rule was checked, but only on `*.md`, `*.mjs`, `*.py` and `*.sh`: a schema or a preset is published just like a document, and `schemas/_policy.json` declares the same rule. Now the search covers `*.json` and `*.yml` (canary: a path in `improvement-verification.json`). And E12 checked that every subcommand was documented, not that every documented flag exists: a non-existent flag is discovered in the operator's terminal. Canary: `--proyecto` in `docs/usage.md` |
| E23 | The promise of privacy was verified against a file without secrets | HECHO 2026-10-01 | The README states that API keys are never read and `_read_settings_structure` documents that it only returns structure, but the common fixture wrote a `settings.yaml` without any key value: the promise was verified against a file with nothing to filter. The new regression writes secrets under multiple field names and requires that none reach the result, while checking that the structure is still what the check needs. Canary: a parser that returns the raw file |
| F5B | Local codebase index (draft layer B) | DECLINADO 2026-10-01 | Three reasons measured, in `docs/external-orchestration-draft.md`: doubles the range that `dsh-tool-fs-search` already gives to every generated mode; its dependencies (`tree_sitter`, `sqlite_vec`, `fastembed`, `onnxruntime`) are not distributable in this tree; and its own invariant—"the index is a locator, it doesn't prove anything"—takes it out of the tree of what the framework gets right. **What changes the decision:** a campaign that measures navigation tokens above what `fs-search` covers and that models the token structure the modes are missing |

## Dependencies
```text
C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7
          └──── discovery/design/test/generation internos ────┘
```
C0 can prepare fixtures, schema and validators in parallel. C4 can be designed while C2 is progressing, but is not accepted until C3 validates an actual packet. C6 should boot from clone and DSH with provider already configured, not from preconfigured image.

## Creator internal capabilities

These are not user end modes:
```text
creator-project-discovery          (audit)
creator-project-documenter         (document)
creator-contract-and-risk-mapper   (audit + architect)
creator-capability-partitioner     (scope)
creator-capability-designer        (architect)
creator-scenario-author            (test)
creator-skill-generator            (develop)
creator-generation-repair          (debug)
creator-drift-analyzer             (sync)
```
The final result per project remains:
```text
<Proyecto>-auditor
<Proyecto>-continuous-repair
+ skills específicas justificadas
```
## Comprehensive pass on real DSH (2026-10-10)

It is not a row of the previous matrix: it is the result of executing the flow on a
real installation of `@deepseek-ai/dsh` `0.2.0-rc.2` with a **dummy** product and
an isolated campaign `DSH_HOME` outside of the canon. The detail per block, with
command and artifact, is in [docs/status.md](docs/status.md).

| Check | Status |
|---|---|
| Real inference pipeline (`dsh --profile headless --json`) | HECHO — `PING-OK`, `completed`, `totalTokens = 6552` |
| Real auditor on a real finding | HECHO — persisted `evidence/audit-finding.md` with excerpt and test exit |
| Real repairer with verified candidate | HECHO — commit `ab5c0c6`, diff `+1 -3`, tests PASS, product intact |
| Real implementer with requested change | HECHO in a single case — commit `95aa9b2`, 6/6 new tests |
| Workflow FAIL → repair → PASS | HECHO — `r-5d7d11…` RETAINED by gate, `r-7761c0…` COMPLETED |
| Skills loaded and invoked in real session | HECHO — 3/2/1 per role; trivial turn → 0 |
| Real abstention without authorization | HECHO — `Decision: I abstain`, product intact |
| Host validator over real package | HECHO — 10/10 layers PASS |
| Corpus gate anti-fraud | HECHO — rejects made-up candidate (0.488 < 1.000) |
| Confinement of the canonical | HECHO — write denied; escalation rejected without channel |
| **Creator end-to-end** | **PENDIENTE** — the real turn did not persist `generated/generation-manifest.json`; the run is `RETAINED` |
| **Corpus gate with real mode** | **BLOQUEADO** — without `dsh web` there is no RPC `session/create` or endpoint `evaluator`; gate abstained fail-closed |
| **Sibling `worktree` of the product** | **BLOQUEADO** — `git worktree add` crashes due to `workspace-write` sandbox; the candidate became a clone within the workspace |

**Debt opened by this pass:**

| ID | Unit | Closing criterion |
|---|---|---|
| X1 | Repair candidate without product `worktree` | Provisions the candidate as a shadow repository created by the Host under the workspace, with its own `.git`, verified against real DSH and without writing to the product's `.git`. Today only `kind=implement` does it. |
| X2 | `dsh web` usable, or Creator without it | The campaign home web profile actually boots (with `node_modules` present) and the package is persisted by the Creator, or the Creator path is demonstrated in a way that does not depend on the web server. Without one of the two, C2 is not revalidated. |
| X3 | Corpus gate against a real mode | The gate runs its 55 cases on a real mode of a real DSH session; today he abstains from naming him. |

## Update rules

1. Only `HECHO` is marked with recoverable evidence and relevant negatives.
2. A material design change first updates `ARQUITECTURA_FLUJO_AGENTES.md`.
3. Do not import profiles, candidates, private paths, sessions or logs into the repo.
4. Creator can never close its own stage as accepted.
5. Backup present does not equal proven rollback.
6. A valid schema does not equate to a useful or safe skill.
7. The history of C0–C7 goes in Git/CHANGELOG, not as a journal in the architecture.