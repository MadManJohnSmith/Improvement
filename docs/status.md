# Checked status of the framework · [Spanish translation](status.es.md)

**Update:** 2026-10-11
**Current architecture:** [v3.0](../ARQUITECTURA_FLUJO_AGENTES.md) (C0–C7 completed; U6 campaign partially implemented, without operational acceptance; lifecycle EN CURSO/IMPLEMENTED_NOT_VERIFIED)
**Progress index:** [C0–C7 and post-C7](../PLAN_IMPLEMENTACION.md) · [one-page view of all milestones](progreso-agentico.md)

This document records only the current status. The detail of previous iterations is in Git/`CHANGELOG.md`, not here.



**Implementer (partial, acceptance in only one real case):** the Host/Creator contract supports a third preset `implementer` in new generations and preserves the two-role ones; the transaction tests local publication of all three. `mode_lifecycle.provision_implementation` binds an exact request and a clean base to an isolated shadow in the workspace, keeps dirty work when resuming and `verify_implementation` measures the diff and runs a behaviour case against the candidate (it does not yet validate that the command is an entrypoint of the Host plan); the regressions demonstrate it against external temporary products. **On 2026-10-10 a real DSH turn** on a fictional product left an external candidate with commit `95aa9b2`, 6/6 new correct tests and the product without the requested field, without implicit commit/merge/push: the mechanism was exercised, in a single case and with the candidate created as a clone within the workspace. `skill_router` only selects over a roster whose definition/entrypoint/bundle/receipt are bound to the manifest of the ACTIVE generation; abstains if evidence, budget or integrity is lacking. **Skills were indeed loaded and invoked in a real DSH session** (auditor 3, repairer 2, implementer 1; a trivial turn did not load any), but `skill_router` is still just an informational selector and has not been exercised against a real session. **Repair no longer asks the product for a `worktree`**: `mode_lifecycle.provision_repair` creates, from the Host, a shadow repository with its own `.git` under the workspace and the session only verifies and registers it (contract `Host-provision_repair-shadow-only`). **Proven in two distinct external trials, with a tightly bounded limit**: under real headless DSH (`x1-live`) the Host shadow, `PROVISIONED → DIRTY`, the verified diff, tests 3/3 and the exact resume were exercised, with the product intact; under web RPC with a real preset and `bwrap` (`x1-preset-real`) the preset resolved, loaded its skill and ran the sentinels, but the supervisor stopped the turns on budget **before editing** (99,022 measured with 128,213 projected, and then 97,973 with 127,227, against a ceiling of 120,000 per turn; the campaign accumulated 243,165 totalTokens); **on 2026-10-11, with the ceiling raised to 200,000, the mode completed the edit and then the closure**: 11 steps and 180,107 billable tokens for the repair (`Math.round(valor)` → `Math.round(valor * 100) / 100` and the VAT-inclusive total rounded over an already rounded rate), with the canonical product intact. In a later turn, **with the commands already published as files verified by digest**, the mode closed the cycle: it emitted `__IMPROVEMENT_CANDIDATE_RECORD__` with `status: DIRTY`, `candidate_diff_digest` and `changed_paths`, persisted it into `work-items.json` and ran the product's entrypoint against the shadow (3/3 green). The entire cycle under a real preset is therefore **proven in both stretches**, with the caveat that the mode persisted that `DIRTY` record by editing the state file, not through the canonical record command. Mechanical bash confinement in a campaign remains untested. The user workflow is entered through `bootstrap workflow run`, not through a mode plugin; the prohibition of delegate/subagent/workflow rows stands. There is no remote publishing.

**Repair integration and retirement:** the Host shadow shares no ancestry with the product;
the operator obtains and reviews a complete diff, including uncommitted changes, before deciding
whether to apply a patch and verify it on the product. `candidate_diff_command` records identity and paths;
it does not deliver a ready-to-apply patch. `shadow_candidate.patch_digest` compares `shadow-base`
to `HEAD` and does not cover uncommitted work. `state_reconcile.retire` checks the identity of worktrees
from the previous design and of current shadows, but **ABSTAINED** before deleting either, even with
exact evidence of integration: neither `git status` nor the receipt inventories all disposable content.
Retirement of either remains the operator's manual decision. Earlier worktree pilots are history, not
current integration instructions.

## Checked technical base

The repository keeps reusable Host services and regressions:

- idempotent external onboarding, manifest and managed links;
- SHA-256 inventory/partition and fail-closed coverage;
- mission contracts, checks and documentary verification;
- idempotent local publisher and role stages;
- durable budget, decisions and append-only metrics;
- Host controller with locks/reconciliation/cancellation;
- isolated Linux launcher and limited inference channel;
- write plugin with corrected escalation semantics;
- QA, semantic re-audit, archive/restore and process/container crash all demonstrated;
- private distribution over the network and clean-room of the base code demonstrated.

These capabilities constitute the checked MVP base. They are not equivalent to the 3.0 onboarding flow or final modes for new projects.

## Validity removals (Eliminaciones de vigencia)

- There are no generic Auditor/Repair presets in the canonical distribution.
- There are no universal operational MVP skills in the current tree.
- There are no P0–P9, M1–M8 plans or v2.4 diagrams in the current documentation.
- The names/configurations used in test projects are not defaults.
- The two-file Creator contract was replaced by the full generation package.

The removed history remains available in Git and must not be reconstructed as current instructions.

## Approved skills strategy

Creator first selects the immutable base library and the specialized pattern catalog; then composes or applies declarative overrides. It only generates an extension when it demonstrates that those layers do not apply, with contract, scenarios and specific acceptance. A transferred skill is not automatically valid for another project. Regeneration does not replace bases for convenience.

The evaluated external sources are registered with provenance set to `library/source-registry.json` (schema `source-registry.schema.json`): 50 sources — 27 repositories of skills/indices/runtimes and 23 standards or guides, with `fastapi-pydantic-docs` replaced by `fastapi-framework` and `pydantic-framework` set by direct observation — with canonical URL, commit, date, license, status and reasoned decision. A source without revision pinned or with an unresolved license cannot be `CANDIDATE` or `ACTIVE`; The acquisition is only manual with pin, without npx/marketplace/downloads, with staging outside the tree and prior Host validation. The detailed inventory that supports the decisions is maintained in an external audit space; the registry only retains its SHA-256 digest. The surface of discovery of new sources is the search `topic:claude-skills` of the GitHub API, filtered by verifiable facts (licensing, maintenance, testing) and with adoption only by analysis by skill with manual pin; freshness never orders.

The base library is materialized in `library/library.json` with content and scenarios in `library/base/`. Base conversion is complete: 21 skills (own reimplementation with MIT attribution of `obra-superpowers` and `addyosmani-agent-skills`) — brainstorming, writing-plans, executing-plans, systematic-debugging, test-driven-development, requesting-code-review, receiving-code-review, verification-before-completion, finishing-a-development-branch, spec-driven-development, constraint-driven-development, source-driven-development, security-and-hardening, context-engineering, api-and-interface-design, observability-and-instrumentation, documentation-and-adrs, performance-optimization, incremental-implementation, code-simplification and deprecation-and-migration. Each base skill has one positive scenario and at least one FAIL/BLOCKED verdict, and coverage is bidirectional and mandatory in the suite. idea-refine, interview-me and using-agent-skills were rejected as a basis for being meta or interactive without universal value.

The specialized catalog contains four evidence-triggered patterns, with content in `library/catalog/` and own scenarios: `fastapi-openapi-contract-check` (domain `python-backend`, source `fastapi-framework` fixed by direct observation), `web-accessibility-wcag-audit` (domain `web-frontend`, source `wcag-22` fixed by specification version — 2.2, W3C Recommendation 2024-12-12 —), `http-security-headers-verifier` (domain `web-platform`, source `mdn-web-docs` fixed by mdn/content snapshot) and `aws-iam-policy-static-review` (domain `aws-security`, source `aws-waf-apg` fixed by awsdocs/iam-user-guide snapshot). All are activated only by observable signals declared in their contract; The declared activation criteria must appear verbatim in the pattern content, and regression requires it. Versioned standards are set by `spec_version` (extended library and registry schema); The pin per commit is reserved for repositories. The catalog no longer receives patterns without evidence of mastery and specific acceptance.

Creator dispatch is automatic from `bootstrap install` and from `creator_client.py`: a single healthy DSH Web instance is reused or a single one is started from the common parent, and the local DSH session (injected client, `DSH_HOME` or standard homes) is acquired and generation is supervised within budget; without an authenticated session, the run remains `CREATED`/`PREPARED` recoverable with the specific action, and `--launch-dsh` allows `dsh web` to be started explicitly. The single Creator session is created linked to the run workspace (`workspace/create` + `workspaceId`), without evaluator/reviewer sessions or delegation. Creator produces exactly two user presets; the Host prepares `<Proyecto>-workspace/mode-state`, materializes an `@deepseek-ai/dsh-agent-preset` declaration bundle, installs it through `pluginManager/installBundle` and and demands real confirmation from `agentPresets/list`. Prior acceptance is deterministic (`READY_FOR_INSTALL`) and does not assert dynamic evaluation; `ACTIVE` follows only a verified publication and roster. Launch applies the `cordis-patch.yml` (`dsh web --patch`) overlay, which loads `workflow_write` with the corrected sandbox resolver, and the versioned prompt prohibits all use of `sandbox_permissions`/`justification` and lifts that prohibition for each delegated subagent. DSH is never downloaded or installed at the initiative of the framework.
Creator selection is integrated with the library: `bootstrap install` freezes a validated snapshot of the library in the run, the versioned Creator prompt lists the base skills and catalog patterns with their activation criteria, contracts that reuse `base-library` or `specialized-catalog` must declare `reuse_reference` with the exact entry, and the Host validator resolves those references against the run snapshot. Transactional activation requires an explicit Host ACTIVE verdict and the base identity is derived by the same method in `install` and `update`.

## Target end experience

```text
user configures DSH/provider once
→ bootstrap install
→ Creator discovers/designs/generates specific modes and skills
→ Creator invokes accept
→ Host validates and supports
→ automatic acceptance
→ transactional activation or rollback
→ user operates <Project>-auditor and <Project>-continuous-repair
```

This experience is implemented (C0–C7) and in hardening on a real pilot; the current dispatch detail is in the architecture §7-B3 and the use in [usage.md](usage.md).

## Current limits

- `THIRD_PARTY_NOTICES.md` added for MIT attribution from jsmastery-pro/skills, and expanded to
  `obra/superpowers` and `addyosmani/agent-skills`, which are the upstreams that the library itself
  declared in each `## Procedencia` and that until now did not reach the public notice (E20).
- Remote publishing and public release require the owner's authorization, per the distribution policy.
- Physical power loss and hostile remote descendants carry no full guarantee.
- Configuring a provider in DSH is the user's prior responsibility; the framework never obtains API keys.
- Pilot hardening requires real evidence: a prompt or a declarative state does not accredit autonomy, skill loading or isolation.

## What tests are not run here

The published count ("NNN tests green") is not the total, and saying so is
exactly what makes it publishable. The current figure is **measured**, not remembered:
`python3 -B -m unittest discover -s tests` closed on 2026-10-11 with
`Ran 1088 tests … OK (skipped=11)`. Regressions added that same day
(the ones fixing helper publication) left the suite at 1091: the figure
published is measured at the close of each unit, this line documents that run. **Eleven regressions are skipped** on a machine
without the external components, and they all name the missing component:

| absent component | what is lost |
|---|---|
| `DSH_MODULE_ROOT` with the runtime installed | the auditor's 7 confinement tests (`tests/test_auditor_confinement.py`, `EROFS` real against bwrap), the real startup of services (`tests/test_host_launcher.py`) and the same-mode escalation of the plugin |
| `node` in `PATH` | regressions driving the plugin module directly |
| `bubblewrap` | durable process/container recovery |
| `jsonschema` | parity of `acceptance-plan` with its JSON Schema (pure Python validation still runs) |

None is an unconditional skip, and a regression that is skipped without naming a
component that the repository does not distribute can no longer exist:
`tests/test_architecture_consistency.py` checks this over the text of each
`skipTest`.


## C0–C7 — completed

| Stage | Status | Output required |
|---|---|---|
| C0 | HECHO | schemas/fixtures/manifests/contracts/tests/handoffs/drift and provenance |
| C1 | HECHO | `bootstrap install` deterministic and resumable |
| C2 | HECHO | a real DSH Creator session (cordis preset) generated a project-specific package and called accept |
| C3 | HECHO | fail-closed 10-layer Host validator verified over the real C2 package (READY_FOR_ACCEPTANCE) |
| C4 | HECHO | verified backups, staging, atomic swap and rollback verified over a real package |
| C5 | HECHO | Creator called accept; Host ran static validation, an evidence ledger and a verdict |
| C6 | HECHO | clean-room pilots run on a Python project and a multipart project with real DSH |
| C7 | HECHO | run reconciliation, THIRD_PARTY_NOTICES.md (MIT) and verified promotion |
## Hardening after C7 (real pilot)

Units incorporated after C7, guided by evidence from real DSH sessions; the details and regressions for each one are in `CHANGELOG.md`:

| Unit | Status | Verified content |
|---|---|---|
| Source Registry and Materialized Library | HECHO | 50 sources with fixed provenance; 21 immutable base skills and 4 catalog patterns with scenarios and bidirectional regression |
| Library ↔ Creator integration | HECHO | library snapshot per run, prompt with base/catalog and activation criteria, `reuse_reference` resolved by the Host validator against the snapshot |
| Automatic DSH dispatch and lifecycle | HECHO | detection/shutdown of previous instances, own port 3080 without killing foreign processes, home HMAC cookie, `npx -y` non-interactive with captured output and redacted tokens, usable provider resolver (warning, not blocking; `DSH_PROVIDER_STRICT=1` for hard stop) |
| Session bound to the run workspace | HECHO | `workspace/create` + `session/create` with `workspaceId`; single Creator session, grouped in the UI, a `workspace-write` boundary over the whole workspace, no evaluator/reviewer sessions or delegation |
| Sandbox anti-escalation policy | HECHO | the framework overlay removes `sandbox_permissions`/`justification` from schemas and rejects any residual occurrence before approval; The two generated modes declare the exact contract in lifecycle/persona first-party and their source mounts `./anti-escalation.mjs`. The post rewrites only that row to the absolute path of the guard copied to the bundle—the current DSH record resolves `config.plugins` from `cordis.patch.yml`—and `agentPresets/read` verifies that effective identity; a regression with the actual DSH runtime mounts the exact composition of seven rows, checks ordinary bash and blocks `workspace-write`/`danger-full-access` before passing |
| Transaction with a Host verdict | HECHO | `install` requires `host-verdict.json` ACTIVE tied to the same generation before activating |
| Host acceptance isolated from the Creator | HECHO | Host acceptance harness with an isolated evaluator and reviewer, hidden cases with private predicates, full cardinality required and actors correlated with real DSH turns; deterministic prior acceptance (`READY_FOR_INSTALL`), no dynamic evaluation assertion |
| Mode installation as DSH presets | HECHO | modes with `mode.json`/`preset.yml`/`agent.cordis.yml`/`SKILL.md`; Creator receives from the run the real case-sensitive product/workspace basenames and the exact path of `mode-state`, and and the Host contrasts that structured identity before accepting/installing; install a bundle `@deepseek-ai/dsh-agent-preset`, demand `application=applied`, healthy roster and candidate composition/root via `agentPresets/read`; an update `restart-required` remains recoverable until relaunching DSH and repeating `bootstrap install` |
| Operational gate and bundle-local skills | HECHO | fail-closed compositions with all six rows operational, `dsh-tool-fs-search` configured with `sampleOverCapGlobResults: false` and no delegation/workflow/web/plugin-manager; minimal frontmatter for modes/skills; complete and secure copy to `bundle/skills`, `includeDefaultRoots: false`, absolute root of the bundle and both IDs on receipt |
| Durable Handoff and Automatic Candidate | HECHO (contract; full cycle with real preset EXERCISED IN TWO TURNS) | Exact anti-escalation (denial/error schema → `RETAINED` without retry), preflight and durable receipts. `mode_lifecycle.provision_repair` provisions, from the Host, a shadow with a `.git` of its own and a receipt in `<workspace>/candidates/repair-<digest16>`; the mode verifies that identity, records `PROVISIONED` before editing and `DIRTY` after, with content digest and list of regular-file paths. Resume only the exactly registered candidate (`resume_policy: exact-recorded-only`); changed base or product, collision, symlink, missing receipt or discrepant identity retained without adopting or deleting another's work. The auditor keeps the handoff and does not write the product. real headless DSH in X1 exercised `PROVISIONED → DIRTY`, the diff, tests 3/3 and exact resume with the product intact; X1 with real web preset loaded the skill and sentinels and, in the 120,000-per-turn ceiling series, the three turns stopped for budget before editing (243,165 `totalTokens` accumulated; 97,973 measured with 127,227 projected in the last; skill, layout and provision alone cost 48,694). With a ceiling of 200,000, the turn reached editing (180,107 measured, 11 steps) and a subsequent turn closed the cycle: the mode registered `DIRTY` with digest and paths, persisted `work-items.json` and executed the entrypoint (3/3). The tests run immediately after the edit were run from outside by the operator; in the later closing turn the mode itself ran the entrypoint (3/3). The three earlier campaigns that created product worktrees and integrated by fast-forward are history, not the current procedure: the operator integrates the reviewed patch, without any shadow-branch merge; `state_reconcile.retire` does not erase shadows: ABSTAINED before them, even with exact evidence of integration. No mechanical isolation or multi-file CAS/lease is claimed from the contract. |
| Tardis pilot (Syncify) | HECHO | each pilot exit became a flow change and regression. Syncify closed the loop with 77 findings persisted and served by modes, integration only by commit/fast-forward/operator push, and green CI (Rust + frontend + Python) at `b9413eb`; closing log declares D-01..D-04 as conditional scope, not backlog: SoundCloud/Apple Music depend on owner credentials. The audit also found that the `candidate` record written by a generated mode may not comply with the schema (own form instead of the contract), so the preflight would archive it silently; that hardening unit is G1 and is closed |
| Clean installation from start to finish | HECHO | uncontaminated environment (new Improvement and RehabWeb clone, new DSH home with only credentials and models, initial roster of four factory presets) and a single `bootstrap.py install --project … --launch-dsh` that produces `Host: ACTIVE` with `rehabweb-auditor` and `rehabweb-continuous-repair`; then a simple audit prompt persisted 45 findings with handoff and a six-word prompt repaired two CRITICAL on a sister candidate, with the product intact until the operator integrated |
| Public launch preparation | HECHO | G1–G3, base re-pinning and G7 (verification against the real stack, without stubs) implemented and in green suite (743 tests): `recording_command` and `reconcile_command` emit the exact JSON object to persist verbatim (relative path, head in base) —root cause of the RehabWeb pattern of candidates with extra fields or absolute path—, the person prohibits adding/changing fields, the preflight returns a report that names what it discards and the installation includes it in its output; `decisions.py` and `metrics.py` are no longer orphans and are wired at the close of the Host controller's shift (event `turn` in `metrics/`, decision ratified in `decisions/`, fail-closed with reconcilable unit); active state earns `overflows.jsonl` as overflow receipt (Syncify 50/50 handoffs case). G7 also closed with the LoboApp campaign: the plan names the capacity by the route with which it can be invoked (a bare `flutter test` was an unfair `BLOCKED`) and distinguishes "can run" from "this session can write to it", asking to materialize with `cp -al` an SDK that rewrites itself under `<workspace>/.stack/<stack>/` (17,659 files, 0 bytes of disk). G0 was closed on 2026-09-30 with Apache-2.0 license chosen by the owner and `LICENSE` in the root, G5 on the same day with README, non-technical quickstart and feedback policy, and G6 with the tag `v0.1.0-beta` published under authorization of the owner; plan in [docs/plans/10-lanzamiento-publico.md](plans/10-lanzamiento-publico.md) |
| Managed State Counting and Reconciliation | HECHO | `persisted_count` stopped being an assertion of the mode: a central `count_command` recalculates from `findings.jsonl` the findings `OPEN` of the declared base, demands that the handoff covers them exactly (mechanical rejection in `workflow_write` before writing, with `persist_order` declared) and prints the number that is reported. `PARTIAL` is decided as a derived verdict, not as an enum value: one record per entrypoint with PASS/FAIL/BLOCKED and worst result winning, and PASS/FAIL contradictions rejected. `scripts/state_reconcile.py` and `bootstrap.py state` reconcile the state with the repository: integrated head that a history rewrite deleted (with `--repoint` bounded and receipt in `overflows.jsonl`), findings `OPEN` with work item `VERIFIED` and findings that no handoff took; `--retire` checks the identity and integration of a worktree `INTEGRATED` **from the previous design** but refrains before deleting the branch or worktree; It also abstains from the current shadow without ancestry, so its withdrawal is a manual operator review |
| Finding evidence anchor | HECHO | `evidence.path` + `evidence.excerpt` with `line`/`located` calculated by the tool before the write-intent: the missing or ambiguous fragment rejects the write instead of resolving, and a finding with no possible location is persisted without an anchor, visible in `anchors`. The field is optional in the schema to not archive historical evidence: an old five-field record is still valid. Technique taken from `alibaba/open-code-review` (`internal/diff/resolver.go`) and registered on `library/source-registry.json` with pin `a758d9c`; the RSI design of `microsoft/skillopt` is registered as `CANDIDATE` without adopting its engine |
| Holdout gate for skills library | IMPLEMENTED_NOT_VERIFIED | `scripts/corpus_compiler.py` compiles the 55 scenarios of `library/` into deterministic executable cases linked by `corpus_digest`, and the oracle is derived in the Host: the public case carries `task`, fixture and `evaluated_claim`, never the expected verdict. `bootstrap.py bound-skill-gate` scores observations **linked** to corpus, candidate, and compiler version; `bootstrap.py skill-gate-commit-check` requires an accepted report when the corpus changes and treats `abstain` as a block, not a permit. Tested with the four decisions against the real corpus. **It remains unverified against a mode**, and the operational reason is no longer just the provider: `skill-gate-run` requires a Host evaluator adapter that verifies before `session/create` the layout per case and the effective skill of each of the 25 objectives; the CLI does not offer it, so today it abstains (`scripts/skill_gate_run.py:604-608`). The 55 cases are 25 skill cases, not auditor mode tests, and an actual SC-123 attempt gave `NOT_COVERED` for targeting/layout, not measured improvement. Auditor's mechanical confinement, measured separately |

### Workflow executor on the Host (U1–U3) and default campaign (U6)

Units U1–U3 of the approved plan for `/workflow` on DSH; the details and regressions for each one are in `CHANGELOG.md`. What is implemented and tested for U1–U3 is pure Host, without a real DSH session — and this is how it is declared:

- **U1 · executor without DSH.** `scripts/workflow.py` executes JSON plans with steps `gate`/`join`/`fase`, a fail-closed validated plan (unique ids, antecedent and acyclic dependencies by construction, known types), an external run dir `<workspace>-workflow/<run_id>/` with mode 0700, and journal append-only with digest chain and atomic checkpoint `head.json` (pattern `metrics.py`); resumption by replay skips only one step with `STEP_COMPLETED` verified by digest, and `verify` re-verifies the chain by replay and fails closed upon alteration, truncation or extension. Outputs as command-decision: `RUN_COMPLETED` (exit 0) and `RUN_RETAINED` with cause (exit 1).
- **U2 · bootstrap entry and abstention.** `bootstrap.py workflow run|verify` with nullable `--run-root` and acquisition of the DSH client via no-launch (never launches `dsh web`); faced with a plan having a step `ask` and no available client, **abstains**: nothing done, nothing written, no run dir, naming the missing piece (exit 1).
- **U3 · step `ask` tested with fake client.** New DSH session per attempt with the verified project preset (`agentPresets/list` + exact operational composition incl. `./anti-escalation.mjs`), `request_id` deterministic by (run, step, attempt), poll with transitive quiescence fail-closed, deadline with `cancel_session` + grace and `RETAINED`, transport errors converted to `RETAINED` with cause, and resume [corr-3]: the live session of a non-terminal attempt receives the same `request_id` or its transcript is re-observed; lost session is `RETAINED`, never resend to new session. No real DSH: Tests use an injected fake client.

U1–U3 regressions: `tests/test_workflow_executor.py`, `tests/test_workflow_bootstrap.py` and `tests/test_workflow_ask.py`; their earlier counts (14, 5, 8) do not include the U6 regressions added to those files.

**U6 · default campaign plan (implementation, not acceptance).** `scripts/campaign_plan.py` generates the deterministic bytes of a v1 plan, manifest with digest and prompts under `.dsh-managed/campaign/` after publishing verified presets; `rondas_max` is 2 by default. `scripts/transaction.py` writes it after activating/publishing presets and returns a receipt; `RESTART_REQUIRED` leaves only `pendiente-de-activacion`, `NO_OP` materializes or preserves the bytes without rewriting, and rollback restores both `capability-plan.json` and the campaign directory. The default plan does not declare `join` dependencies: the eight steps are executed in order. These are tests of the mechanism, not an actual completed campaign or an acceptance of U6.

| Default step, in order | Function and documentable result |
|---|---|
| `preflight` (gate) | Checks manifest, DSH presets and stacks: PASS (0) or BLOCKED (2); BLOCKED retains the run and does not accredit an audit. |
| `auditar` (ask) | Uses the auditor preset; produces `evidence/campana/auditoria.json` if complete; without a verified client/preset it abstains before the run. |
| `verificar-pre` (gate) | Derived from the product ledger `evidence/veredicto.json`: PASS (0), FAIL (1) or BLOCKED (2). FAIL continues as a failed step, BLOCKED retains. |
| `reparar-1` (ask) | Declares the repairer preset conditional on a `FAIL` from the previous gate; today with FAIL it holds without being dispatched (see the limit below); with PASS it records `ASK_SKIPPED`. Contracted result: `evidence/campana/reparar.json`. |
| `verificar-post` (gate) | Re-derives PASS/FAIL/BLOCKED from the ledger; FAIL continues, BLOCKED holds. |
| `reparar-2` (ask) | Conditional on a `FAIL` from `verificar-post`, under the same contract; today with FAIL it retains, with PASS it records `ASK_SKIPPED`. |
| `verificar-final` (gate) | PASS/FAIL/BLOCKED from the ledger; FAIL aborts and holds, BLOCKED holds. |
| `cerrar` (gate) | Issues only PASS (0) without reading the ledger; it does not in itself prove that the previous verifications passed. |

The `result_contract` of each ask requires `path` and allows `evidence_name` (default `.`); `if_veredicto` reads `evidence/veredicto.json` from the previous gate and emits `ASK_SKIPPED` if it does not match. Loading results confines paths/symlinks and applies budgets (200 files, 8 MiB per file, 256 MiB per root, result JSON up to 1 MiB): exceeding them holds. The static preflight of joins rejects on load a record larger than 4096 B (50 dependencies accepted; 55 rejected in regression). `scripts/campaign.py` only reads the ledger `mode-state/verification-results.jsonl` of the product, **does not write it**: without capacity the value is BLOCKED; with capacity but no usable records, FAIL. The verification gates write BLOCKED as a value of `veredicto.json`, there is no event `BLOCKED` of the journal. The FAIL→repair dispatch **works**: a gate that exits 1 with `on_fail: continue` registers `STEP_FAILED` and remains at `failed_gates`, which `if_verdicto` accepts as a source (`scripts/workflow.py:1547-1553`), so the ask conditional on its `FAIL` is dispatched and the run ends `RUN_COMPLETED` (regression: `tests/test_workflow_ask.py:682-703`). What has not been tested is the full cycle with real DSH or the canonical product.

**System 1 channel (designed, not implemented).** The design of the decision models channel as an advisory proposal is in `docs/plans/system-one-decision-channel.md` and its prerequisite —wrapping `session/selectModel` in the client— **is already implemented and verified** (`4352a55`): it was the blocker that prevented exercising the level of reasoning per step. The versioned rubric with digest and the findings deduplication pilot remain to be implemented. No evidence claims that a decision model has decided anything.

**What does not exist yet:** acceptance of U6 or campaign run with real DSH. The previous live poll ended at `plan ilegible` ​​(no run dir or journal), not PASS. There is also no event `BLOCKED` of its own, `schema_version: 2`, `gate.cwd`, two separate plans, Host writing of the ledger, `bootstrap campaign` or universal code classification; integration with `acceptance.py` remains an open risk. U4 (bundle) was not executed and requires explicit authorization; U5 (skill-doctrine at `library/`) was not executed and requires library gate with real operator session.

### Comprehensive pass on real DSH (2026-10-10): what was measured and what was not

On 2026-10-10 a test was run with a real installation of `@deepseek-ai/dsh` `0.2.0-rc.2` (committed version with `npm view`), an isolated campaign `DSH_HOME` outside the canonical one and a **dummy** product with real git and a known defect. Nothing touched the operator's actual product or `~/.dsh`. Artifacts live outside the canonical repository. The verified procedure to reproduce the session remained as a permanent skill: `skills/dsh-maintenance-session/SKILL.md`.

**Checked in this pass, with command and artifact:**

| Check | Result |
|---|---|
| Real inference pipeline | `dsh --profile headless --json` with `DSH_HOME` isolated: `final.text = "PING-OK"`, `turn_end.reason.kind = completed`, `totalTokens = 6552`, exit 0 |
| Fictional fixture in red | `FAILED (failures=1)` `70 != 30` before repair |
| `bootstrap install` | run `CREATED`, run dir external to canonical |
| Royal Auditor | 13 tool calls, `evidence/audit-finding.md` (2,030 B) with literal excerpt and test output |
| Real repairer | external candidate `candidate-repair-ensayo-1`, commit `ab5c0c6`, diff `+1 -3`, PASS tests, intact product |
| Real implementer | candidate `candidate-implement-nivel`, commit `95aa9b2`, 6/6 new tests OK, product without `nivel_alerta` |
| Workflow FAIL → repair → PASS | run `r-5d7d11…` `RETAINED cause: gate-abort:gate-producto`; run `r-7761c0…` `COMPLETED` |
| Journals | `workflow.py verify` VERIFIED in both run dirs |
| Campaign report | `MEMORY_RECONCILED {base 693ba47…, invalidated: 6, hits: 0, misses: 0}` |
| Skills in real session | auditor uploaded 3, repairer 2, implementer 1; trivial turn → 0 tool calls |
| Royal abstention | turn with `Decision: I abstain` verified with write-probe, product intact |
| Host Validator | `READY_FOR_ACCEPTANCE`, 10/10 layers PASS on real package |
| Corpus gate anti-fraud | `action: reject` — invented candidate loses in training partition (0.488 < 1.000) |
| Canonical confinement | attempted write from canonical repo denied; retry with `danger-full-access` rejected without approval channel |
**Not proven (stated, not filled with assumption):**

1. **`dsh web` does boot on this machine; starting the server was never the problem.**
   Checked on 2026-10-10 with actual installation `@deepseek-ai/dsh` `0.2.0-rc.2` outside the
   canonical: `dsh web --port 17999` printed `dsh web: http://127.0.0.1:17999/?token=…` and
   He continued serving until the cut, with an empty `DSH_HOME`. The pass of 2026-10-10 copied
   `profiles/web/` **with `node_modules/` empty**, and there the server did not lift; that was the
   real reason for that stoppage, not a lack of product. **What is still missing is the
   Host evaluator adapter per case**: the dispatch of the corpus gate goes through the session API
   real (`session/create` + `session/prompt` + `session/page`) —no endpoint exists
   `evaluator` in DSH 0.2.0-rc.2 (bug from a previous revision,
   `scripts/skill_gate_run.py:64-83`, regression on `tests/test_corpus_gate.py:623-631`)—, and
   Before creating a session, the runner also requires that the adapter verify the compatible cwd
   by case and the effective availability of each target skill; without that it abstains fail-closed and without spending (`scripts/skill_gate_run.py:604-608`, regression in
   `tests/test_skill_gate_run.py`). **The corpus is neither a test of the auditor mode nor
   vice versa:** its 55 cases point to 25 concrete skills, and the way you would execute them is
   another artifact. Measured corollary of the pass: the corpus gate
   (`bootstrap.py skill-gate-run`) abstained fail-closed with
   `no hay sesión DSH utilizable: … No .credentials.yaml at <HOME>/.config/dsh`
   (`scripts/skill_gate_run.py:33-44`, `scripts/creator_client.py:1673-1690`). It is worth not confusing four different things: that `dsh web` boots (here it does, with an empty home), that
   an endpoint `evaluator` exists (it does not exist in 0.2.0-rc.2), that a Host adapter exists that verifies layout and effective skill before `session/create` (also: `ABSTAINED` without
   expense) and that the corpus compiles a **skill** and not the **mode** that would dispatch it. The
   fourth is the measured cause of `NOT_COVERED` in the subsequent external test
   (`corpus-fixed`): case `SC-123` pointed to skill `source-driven-development` and the gate
   dispatched to mode `fixture-auditor`, which also required layout `<producto>/<workspace>` that
   the case directory did not have; the gate read only `result.json`, which the mode did not write, and
   abstained fail-closed. Neither that abstention nor that stop at home is a failure of the gate
   which computes: the bound holdout gate (`bound-skill-gate`) continues to decide on
   real observations and rejects the fabricated `PASS`. See
   [progreso-agentico.md](progreso-agentico.md), rows X2/X3.
2. **Creator end-to-end was not proven in this pass** (`Creator end-to-end no se probó`). A real headless turn with the full `creator-prompt.md`
   (29 tool calls, 734,064 tokens, cwd correct) did not persist
   `generated/generation-manifest.json`; the run was `RETAINED`. The package the Host validator accepted in this pass was produced by the framework's deterministic tools from the canonical contract, **not** by the model. **Later, an external trial did generate with real DSH**
   (overlay headless model-facing, manifest `GENERATED` with 19 artifacts, `bootstrap accept` and
   Host → `ACTIVE`), but that trial is **before** the per-run Creator budget accounting correction, so that `ACTIVE` does not accredit post-budget generation nor the current gate. See [progreso-agentico.md](progreso-agentico.md), row X3.
3. **`git worktree add` got blocked by session sandbox.** `git -C <producto> worktree add
   -b <rama> <sibling>` fails with `fatal: cannot lock ref … Read-only file system` more
   `[sandbox: file access denied under workspace-write mode]`; the attempt to climb received
   `sandbox escalation to "danger-full-access" requires approval, but no approval channel is
   available`. That limit is the origin of the design change: the candidate is no longer a
   worktree** but a shadow repository with its own `.git`, provisioned by the Host, and the
   repair provision is implemented with `mode_lifecycle.provision_repair` +
   `shadow_candidate` (contract `Host-provision_repair-shadow-only`,
   `schemas/modes.schema.json`), with negative regression in product fixture `bwrap`
   read-only and writable shadow
   (`tests/test_mode_lifecycle.py:97-146`:
   `test_external_bwrap_read_only_product_writable_shadow_repair_session` and
   `test_host_repair_rejects_legacy_worktree_symlink_and_receipt_collision`).
   **The cycle commands no longer carry the embedded helper.** Packaging the utilities
   (`candidate-diff.py`, `work-items-guard.py`, `finding-ids-digest.py`) as a base64/base85 blob
   inside the command forced the mode to transcribe ~900 high-entropy characters on each `bash` call: a
   real 200,000-token turn lost the cycle closure because a single `+` sent instead of `>` in the payload
   caused `zlib.error: incorrect data check` —with the repair already done and correct—. Now the Host
   publishes all three files in `workspace/.dsh-managed/shared/`; commands verify their SHA-256
   before execution, and the activation receipt publishes all three digests under `published_helpers`.
   Publication covers every branch, including the idempotent one
   (`scripts/transaction.py:_publish_helper`, `scripts/mode_lifecycle.py:_helper_invocation`).
   **The entire cycle under a real preset was exercised in two stretches.** With a ceiling of 120,000
   per turn, the `x1-preset-real` series accumulated **243,165 totalTokens** and the last two
   turns were cut off **before editing** (99,022 measured with 128,213 projected, and 97,973 with
   127,227); Just loading the skill, the layout and provisioning the shadow cost 48,694 tokens. With the
   ceiling raised to 200,000 the turn **did edit**: 11 steps and 180,107 billable tokens, the shadow
   got dirty with the canonical defect fixed (`Math.round(valor)` → `Math.round(value * 100) /
   100`, and the VAT-inclusive total rounded over an already rounded rate) and the canonical product
   was left intact. The turn stopped on projection (180,107 measured versus 208,828 projected)
   before closing. In a later turn, and with the commands published as files
   verified by digest, the mode closed the missing section: it emitted
   `__IMPROVEMENT_CANDIDATE_RECORD__` with `status: DIRTY`, `candidate_diff_digest` and
   `changed_paths`, persisted it in `work-items.json` and executed the product entrypoint against
   the shadow with 3/3 in green. The tests run immediately after the edit were run by the operator from outside; those of the closing turn were run by the mode.
   **Measured context cost; cause and sufficient ceiling not yet established.** Measured on the
   journal of the turn (`/tmp/x1journal/final.jsonl`, external to the canonical tree), the contract arrives through three channels in the
   context of every step through three channels: the preset's persona (8,117 characters),
   the skill body (24,635) and the cycle injected by the trial prompt (17,961); sum
   50,713 characters in the context of the first step, and subsequent steps reread context
   accumulated via `cacheRead`. The textual overlap is almost zero—a fragment of
   68 characters between person and skill, 0 shared shell skeletons between the injected cycle
   and the skill—but each channel plays a different role (bootstrap, contract, and trial order). `cacheReadTokens` grows
   monotonically (128 → 4,055 → 12,666 → 12,848 → 15,360) and step 2 cost 21,963
   `totalTokens` for a one-line sentinel. The 200,000 ceiling has already been tested: it was enough to
   edit and verify, and what prevented closing within that same turn was the projection, not the
   ceiling.
   The part before skill loading
   in `persona_prefix` (`scripts/mode_lifecycle.py:571-585`) it is necessary and is not trimmed; the
   Subsequent operational prose may be trimmed against what the JSON of the cycle already guarantees,
   changing the canonical function and the proofs that fix its exact text
   (`scripts/composition_contract.py:145-153`).
Creator's budget is measured **per run** and evaluated before declaring success: tokens
the real tokens are folded for each observed `seq`, the limit is frozen with the deadline so that
a restart does not relax it, and a final turn that fits at rest but has already exceeded the limit is
retained rather than accepted (`scripts/creator_client.py:_supervise_creator`,
`tests/test_creator_budget.py`). The X3 trial that left the Creator `ACTIVE` was **before**
that accounting correction and does not credit the current gate. The two **post-budget X3**
trials ended `RETAINED` and neither reached `ACTIVE`: the first one stopped with
**1,127,176 totalTokens** against a **1.25 M budget**, leaving 122,824 of margin
unspent, and the second crossed the ceiling with **1,270,969 totalBillableTokens** (1,009,664 of
them cache reads, 79% of the bill). DSH charges for a model step
indivisibly, so a journal observer cannot stop exactly at the ceiling: the
last step is the one that crossed it. In both the model continued reading schemas without manifest or
`turn/end`. Each figure was recalculated separately by decompressing the whole durable journal and
matched the live accounting.

No cost in money was measured in this environment either: it is declared in tokens (≈1,456,519 tokens in the
six turns with measured usage). The pass is a sample of a fictitious product, not a campaign
on the operator's real repository.

### `stack_coverage`: which stack is tested and which is just declared

Thirty stacks declare how to verify themselves. **A handwritten command is not coverage**, and the
difference has to be seen before anyone trusts it on their repository.
`tests/test_stack_coverage.py` puts a real toolchain in the `PATH` of each stack and requires that
the plan names a command the shell can invoke; then removes it and requires the plan to name
the missing capability rather than assuming availability. That turns "declared" into
"resolves or blocks honestly", which is what can be checked without a project in every technology.

The campaign-evidence column retains the plan's literal labels: `PROBADA` means proven
by a real campaign; `declarada` means declared, with resolution checked but no campaign.

| stack | declared command | real campaign evidence |
|---|---|---|
| `rust` | `cargo test`, `cargo clippy -- -D warnings` | **PROBADA** — Syncify (Rust/Tauri/Vue), green CI in 3 jobs |
| `python-django` | `python manage.py test`, `python -m django check` | **PROBADA** — RehabWeb, 108 real Django tests |
| `python-generic` | `python -m pytest -q`, `python -m compileall -q .` | **PROBADA** — el propio framework sobre sí mismo (the framework tested against itself) |
| `dart-flutter` | `flutter test`, `flutter analyze` | **PROBADA** — LoboApp, 166 Flutter tests |
| `node` | `npm test`, `npm run build` | declarada; resolution verified, no campaign |
| `go` | `go test ./...`, `go vet ./...` | declarada; resolution verified, no campaign |
| `java-maven` | `mvn -q test` | declarada; resolution verified, no campaign |
| `java-gradle` | `./gradlew test` | declarada; resolution verified, no campaign |
| `dotnet` | `dotnet test` | declarada; resolution verified, no campaign |
| `php-composer` | `vendor/bin/phpunit` | declarada; resolution verified, no campaign |
| `ruby` | `bundle exec rspec` | declarada; resolution verified, no campaign |
| `deno` | `deno test`, `deno lint` | declarada; resolution verified, no campaign |
| `bun` | `bun test` | declarada; resolution verified, no campaign |
| `android-gradle` | `./gradlew testDebugUnitTest`, `./gradlew lint` | declarada; resolution verified, no campaign |
| `swift` | `swift test`, `swift build` | declarada; resolution verified, no campaign |
| `cmake` | `ctest --test-dir build` | declarada; resolution verified, no campaign |
| `meson` | `meson test` | declarada; resolution verified, no campaign |
| `sbt` | `sbt test` | declarada; resolution verified, no campaign |
| `elixir` | `mix test`, `mix format --check-formatted` | declarada; resolution verified, no campaign |
| `erlang` | `rebar3 eunit`, `rebar3 xref` | declarada; resolution verified, no campaign |
| `zig` | `zig build test`, `zig build` | declarada; resolution verified, no campaign |
| `crystal` | `crystal spec` | declarada; resolution verified, no campaign |
| `nim` | `nimble test`, `nimble build` | declarada; resolution verified, no campaign |
| `julia` | `julia --project=. -e using Pkg; Pkg.test()` | declarada; resolution verified, no campaign |
| `r` | `R CMD check --no-manual .` | declarada; resolution verified, no campaign |
| `perl` | `prove -lr t` | declarada; resolution verified, no campaign |
| `clojure` | `clojure -M:test` | declarada; resolution verified, no campaign |
| `cabal` | `cabal test all` | declarada; resolution verified, no campaign |
| `haskell-stack` | `stack test` | declarada; resolution verified, no campaign |
| `dune` | `dune runtest`, `dune build` | declarada; resolution verified, no campaign |
The twenty-six without campaigns are the real gap in the beta: if your project uses one of them, the plan
solves the command and the framework does not invent a `PASS`, but no one has run one yet
actual suite of that technology against this flow. This is exactly what the beta is for.
discover, and that is why it is asked to share the `mode-state` when the stack is not in the table
tested.

**Current goal:** public beta — anyone with your repo and DSH configured installs
with one command, operate both modes with simple prompts and report by sharing your
`mode-state`. Gates G0–G6 of the launch plan are the operational definition of
“finished” for that goal, and **all seven are closed**: G6 was completed on 2026-09-30 with
the tag `v0.1.0-beta` published under authorization of the owner.

**Open work: none in the `PLAN_IMPLEMENTACION.md` matrix.** D1, D2, D11 and F5
closed on 2026-10-01, along with E1–E5. What remains is not an open row but **evidence that
only the operator can produce**, and it should be named so that it is not confused with work done:

- **The library gate still has not scored observations from a real agent.** The
  executor exists (`bootstrap.py skill-gate-run`), the corpus is executable and the gate decides, but
  running it requires, besides a DSH session with a configured provider, a **compatible
  Host evaluator adapter** that verifies before `session/create` the per-case layout and the
  effective skill of each of the corpus's 25 objectives; the CLI does not offer it, so today the
  command abstains. Without these two pieces the executor **abstains by naming what is missing**,
  which is the right thing to do and not a result.
- **Mechanical confinement is measured and applied as a contract, not proven in a
  campaign.** `tests/test_auditor_confinement.py` tests it against the real runtime with `EROFS`;
  that a real project exercise it under the full flow is what the beta checks.
- **Twenty-six stacks are declared and none have a campaign**; the table `stack_coverage` of
  Above it names them all.

**D11: the corpus is already executable, and what remains is to execute it against a mode.** The 55
scenarios of `library/` were tables of declarative assertions (`contract_declared: true`),
not tasks that an agent might receive. `scripts/corpus_compiler.py` gives them shape
deterministic executable reusing `acceptance_harness._public_input`, and the oracle is
drifts on the Host instead of traveling on the public case. The missing door is to execute:
Producing observations requires a provider that configures the operator, and the framework does not.
installs or invokes it. Until that happens, **no library change has passed through the
gate with evidence from a real agent**, and so it is said.

**D2: the auditor can be confined in the core; the repairer's worktree cannot.**
Against `0.1.7-rc.2` installed, the writable root of `workspace-write` was the session cwd,
and the product sibling to the workspace was **inside** that cwd: bash clobbered it
for real. Pointing the policy at the workspace instead of the session root fixed it —the
product falls outside `writableRoots()`, bash receives real `EROFS` and the auditor **still
can persist its findings**—. In the previous design, the repairer was blocked:
`writableRoots()` admitted **one single** configurable root and needed two, candidate and
shared state; moreover `git worktree add` registered the worktree in the product's `.git`,
which in a confined session is read-only. **That measure was confirmed on 2026-10-10 over real DSH**: `git -C <producto> worktree add -b <rama> <sibling>` returned `fatal: cannot lock ref … Read-only file system` plus `[sandbox: file access denied under workspace-write mode]`, and the candidates were created as `git clone --no-hardlinks` within the workspace, not as sibling worktrees. That is why for that reason the design no longer asks for a worktree: `mode_lifecycle.provision_repair` (+ `shadow_candidate`) creates the candidate as a **shadow repository with its own `.git` under the workspace, from the Host**, with contract `Host-provision_repair-shadow-only` and identity receipt; the mode only verifies and records it. Pending: an intact Creator run that exercises it in a real session.
All of it is fixed in `tests/test_auditor_confinement.py` against the real runtime.

**E6: the memory was written and no one read it.** The closing audit of this
ronda found that `episodes.py` wrote `episodes.jsonl` and `episodes-index.json`
with seventeen regressions proving that registration works, and that no product path
read the index: the documentation said "the auditor consults it before
persist a finding” and it was true of one sentence and false of the framework. `workflow_write`
It calculated the exact signature with which the memory is indexed and discarded it. All the
tests of that day were true; none were about what the unit was for.
Now the query occurs in the same write as the anchor: if the signature is in the
index, the record has `evidence.prior_episode` with the unit that closed it and the
fix that worked, and `bootstrap.py state` counts those repetitions in `repeats`
because a prevention that failed is a different defect from the first. The gap is not
covered with a phrase: it was covered with an eight-case canary-checked regression, and with
another that binds person, contract and plugin so that they do not diverge again without anything
failing.
**Second audit: the same disease, seven times.** A systematic review — an AST pass over
`scripts/` for orphan code, row by row over the forty rows `HECHO` of the matrix, and
contrast between persona, contract, Creator prompt and plugin—found seven more statements that
were true of the document and false of the product. **E7:** the derived verdict was promised in three
places and nobody called `stack.derived_verdicts`, so a partly verified finding had
no verdict anywhere. **E8:** the metrics were written and `metrics.summarize` never
aggregated them. **E9:** the RSI was missing half the reflection — the gate rejected and threw away
the reason, and the next attempt paid for an agent run to receive the same answer. **E10:**
stack coverage was not falsifiable; edit the document to claim a campaign that did not occur
left the tests green. **E11 and E12:** eleven regressions did not run without the runtime and the count did not
say so, and five commands that worked were not in `docs/usage.md`. **E13:** the emitted contract was
measured in bytes but was not validated against its schema. **E14:** seven public functions without a single
product caller, seven were wired up and one was removed for being a second reader of what the
plugin already takes care of. All of them with a canary: breaking any of them makes the suite fail.

**F5 layer B (local codebase index) DECLINED, not pending.** Reason is measured and written
in the draft: doubles the scope that `dsh-tool-fs-search` already gives to every generated mode, its
dependencies are not distributable in this tree, and its own invariant takes it out of the tree of what
the framework gets right.

**Third audit: what was only checked against a fixture.** The two previous rounds
they were looking for prose statements without a counterpart in the code. This changed direction: which repository rules are checked against a single fixture only, and would therefore never touch the
one real case that exists. **E15:** the invariant “plan ready ⇒ executable command” was tested for eleven
synthetic products, and the framework's own `improvement-verification.json` was not resolved by
any test; since `stack.declared()` validates form and not execution, a truncated command would still
resolve to `verification_ready: true` and a real campaign would have registered a product failure
caused by the framework declaration. **E16:** of the twenty-two schemas, three were applied by a
handwritten validator to which no name pointed, and two were addressed with a name that was not
their file's; now the union is declared in the product and the regression requires that
`schemas/` and it be named exactly. **E17:** the README published "743" and "755" sixteen
lines apart, without saying which was current; the count is now discovered, and a figure that does not match has to
declare itself as belonging to another moment. All three have canaries.

The hypothesis that round started with was stronger than its findings: a `cat` dump
showed the declared command without its argument, yet the file's bytes and the resolved plan
demonstrated that it did not. **The suspicion was of the rendering, not of the framework** — and the failure it
was looking for remains reachable, which is precisely what the E15 regression prevents.

**Fourth audit: the two populations nobody read.** **E18:** the golden manifests of
`fixtures/` exist, according to their own README, to validate generators and validators, and their
files do not carry paths or credentials — and no test, validator or module opened anything under
`fixtures/`. The four manifests now validate against their schemas and are checked on each run,
as is the sanitization that the README took for granted. **E19:** `prepare_project_skills` copied the
skills **without parsing them** and selected directories by the mere presence of `SKILL.md`, so a
skill that no loader would read was installed without saying anything and a directory with content but no
`SKILL.md` was left behind without the result naming it. Now it fails closed in both cases and
checks the five real skills in the repository. The test that covered that path used a skill
with literal line breaks that passed only because no one read it.

**Sixth round: the canonical tree rule, unchecked (E21).** `AGENTS.md` requires that
execution artifacts live outside the repository and expressly says that ignoring them in Git is not
enough, but there was only `.gitignore`: nothing prevented a `work-items.json` or a `mode-state/` from being
left inside. Now the suite fails by name on either, with its vocabulary read from
the literals in `scripts/` and a second test that rereads those literals so that the copy does not become
stale — which is how `evidence-ledger.jsonl` and `scenarios.jsonl` appeared in their first run.
`fixtures/` is exempt by design and subject to its own sanitization rule.

**E22 · two guardrails that AGENTS.md required but nobody had installed.** The “no local paths
of the maintainer” rule was checked, but only on `*.md`, `*.mjs`, `*.py` and `*.sh`: a schema or a
preset is published just like a document, and the search now also covers `*.json` and `*.yml`.
And E12 checked that every subcommand is documented but not that **every documented flag exists**,
which is the failure that is discovered in the operator's terminal in mid-flight. Both have canaries.
**E23 · the privacy promise tested against a file without secrets.** The README states that the framework
never reads or asks for API keys, and the provider check documents that it returns structure only. The
fixture that all those cases use writes a `settings.yaml` with no key value: the promise was
checked against a file that had nothing to filter, and would have remained true even if the
function returned the entire document. Now there are secrets in the fixture, under different field names, and none may appear in what is returned.

Regression suite: see last record at `CHANGELOG.md`; the entire suite runs green before each unit closure.