# Project lifecycle modes: domains, boundaries and sequencing

**Status:** design inventory, not a claim of implemented modes. [Español](project-lifecycle-modes.es.md).

Improvement aims to serve the entire lifecycle of a project. A skill is a reusable procedure;
a **mode** is a project-specific, Host-published operational role with an explicit capability
ceiling, state contract, and acceptance tests. The Host still owns authorization, evidence,
publication and verdicts. Multiple skills do not automatically imply multiple modes: create a
new mode only where its authority boundary, output, or handoff differs materially.

## What exists today

| Role | Boundary | Verified status |
|---|---|---|
| Auditor | Reads the product and writes evidence-backed findings/handoff. | Published in real DSH sessions; full corpus gate still abstains without a compatible Host evaluator adapter. |
| Continuous repair | Repairs recorded findings in a Host-provisioned shadow, verifies with the product entrypoint, never merges/pushes. | The real web-preset X1 edit and `DIRTY` close ran in separate turns; not proof of a single autonomous campaign. |
| Implementer | Implements a **new, authorized request**, not an existing finding, in an isolated shadow with a requested-behaviour test. | Contract and three-preset transaction exist; one real DSH case produced a candidate with 6/6 tests, but post-budget Creator `ACTIVE` and a full Host-accepted generated package are **not proven**. `verify_implementation` does not yet enforce that its command is the Host capability-plan entrypoint. Do not mark this role complete. |

The internal Creator capabilities (`capability-designer`, `skill-generator`, context management)
are *generation machinery*, not published project modes. Base skills such as `brainstorming`,
`writing-plans`, `executing-plans`, `test-driven-development`, and ADR documentation are
procedures that an eligible project mode can load; none by itself authorizes writing code or
creates a new role.

## Candidate domains and non-overlapping outputs

| Domain / candidate mode | Input and output | Authority boundary and handoff | Priority |
|---|---|---|---|
| Discovery / analyst | Authorized question plus observed project facts → cited constraints, unknowns and requirements. | Read-only; marks hypotheses, never a verdict or product edit. Feeds ideation or planning. | High, design only |
| Ideation / options | Observed constraints → at least two viable alternatives, trade-offs, discard criteria and one recommendation. | Read-only; `brainstorming` procedure; no plan execution or design adoption without an owner/Host checkpoint. Can be combined with discovery until distinct evidence warrants a separate preset. | High, design only |
| Planner | Chosen goal and constraints → bounded units, dependencies, budgets, tests and stop conditions. | Writes a proposal in workspace state, not the product. Operator/Host approves the plan before any execution. | High, design only |
| Architect / designer | Approved requirements → interfaces, ADRs, migration/rollback and cross-cutting constraints. | May propose technical design but cannot expand scope or self-approve. Works with planning; a separate mode is justified when ADR/interface authority needs its own acceptance gate. | High, design only |
| Implementer | Approved plan/request → shadow diff and behaviour evidence. | Candidate-write and test-execute only in the shadow; cannot rewrite the approved plan or merge. **Finish this existing mode first.** | High, partial |
| Reviewer / verifier | Candidate diff and plan → independently checked test/build/security evidence and review findings. | Read-only against product; may run authorized checks in isolated environment. The Host still judges exit codes/digests and issues the verdict. Could be a workflow phase rather than a permanent preset. | Medium |
| Release / operations | Host-accepted change and deployment plan → release checklist, migration and monitoring evidence. | Publication, push, deployment and rollback remain explicit operator/Host-controlled actions; no autonomous release mode by default. | Later |

Auditor and continuous repair retain their present boundaries. A decision model (System 1) is
**not** a lifecycle mode: it can propose a small typed choice to one of these roles or the Host
and never execute tools or grant authority. See [System 1 design](system-one-decision-channel.md).

## Proposed lifecycle and acceptance gates

```text
request → discovery → options (if genuine alternatives) → approved plan / ADR
        → implementer shadow → independent checks / review → Host verdict
        → operator integration / release → operational feedback → new request
```

1. First finish the implementer: a post-budget Creator package `ACTIVE`, the actual
   project-specific preset loaded in a real DSH session, the Host-plan entrypoint used in its
   acceptance check, and a clean product with a bounded shadow diff. Until then the existing
   one-case evidence remains partial.
2. Pilot discovery+ideation as one read-only project-specific mode or bounded workflow phase.
   Split it only if distinct permissions/handoffs are measured; avoid one preset per skill.
3. Pilot planner+architect as separate gates if the approved plan and ADR/interface design have
   different owners or evidence. Do not pre-approve either from their own prose.
4. Add independent verification before a release-domain mode. Test and build commands belong to
   the Host capability plan; the exit code and captured output are evidence, not a model claim.
5. Measure actual project coverage (languages, stacks, new features, bugs, upgrades, deployment)
   before saying the framework supports "any project" or a full lifecycle.

**Open decision:** the number of final presets is evidence-dependent. The table identifies
*domains*, not a commitment to ship seven modes. Creator should generate only the roles that
have distinct scopes, enforceable capabilities and proven handoffs for that project.
