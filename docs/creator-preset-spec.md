# Generational contract for DSH Creator

> **English (canonical).** A Spanish translation lives at
> [creator-preset-spec.es.md](creator-preset-spec.es.md). The normative terms shared by
> both live in the [Shared terms](#shared-terms) glossary below.

**Version:** 1 (implemented in C0–C5; verified against real packages in C2–C3 and C6–C7 pilots)
**Architecture:** [ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) v3.0

The current contract defines a complete generation; any earlier two-file composition falls
**outside the canonical tree** — *fuera del árbol canónico* — and exists only in Git
history. Creator must generate a complete, project-specific package under
`creator-runs/<generation-id>/generated/`; it never installs anything and never
self-approves.

## Host entry

The generated experience must literally accept novice prompts such as
`Audita completamente este proyecto; no modifiques ni publiques.` and then
`Repara los hallazgos de la auditoría; no publiques.` without asking for paths, JSON,
worktrees or configuration.

Creator receives references to:

- `run.json`, snapshot and inventory;
- project manifest and instructions index;
- authority and runtime capabilities;
- effective routing (no credentials);
- normative templates;
- generic skills;
- contracts/schemas;
- budget and stop conditions;
- a single staging directory.

The product/framework are mounted read-only; writing only happens inside the run. The
Creator DSH session is created bound to the run's workspace (`workspace/create` +
`workspaceId`), so the `workspace-write` boundary is the whole workspace and the session
stays grouped in the UI; the lifecycle detail is in architecture §7-B3. The
configuration/provider already exists in DSH. The framework never receives API keys.

## Skill selection strategy

Creator must resolve each need in this order:

```text
1. library/base            — the immutable base library (`biblioteca base inmutable`),
                              adapted, never rewritten
2. `catálogo especializado` (the specialized pattern catalog, `library/catalog`)
3. composition of several skills
4. limited declarative override
5. the `extensión específica generada` (generated project-specific extension)
6. `RETAINED` if no option is acceptable
```

A new extension must demonstrate that the earlier layers do not apply. A skill
transferred from another project must pass full acceptance in the destination project.
Creator cannot modify controls, holdouts, thresholds, capabilities, the evaluator, the
Host or the acceptance.

## Internal capabilities

Creator composes internally:

```text
project discovery          (audit)
project documenter         (document)
contract/risk mapper       (audit + architect)
capability partitioner     (scope)
capability designer        (architect)
scenario author            (test)
skill generator            (develop)
generation repair          (debug)
drift analyzer             (sync)
```

They are neither final modes nor installed presets.

## Required output

```text
generated/
├── generation-manifest.json
├── project-manifest.json
├── capabilities.json
├── modes/
│   ├── <Proyecto>-auditor/
│   │   ├── mode.json
│   │   ├── preset.yml
│   │   ├── agent.cordis.yml
│   │   └── SKILL.md
│   └── <Proyecto>-continuous-repair/
│       ├── mode.json
│       ├── preset.yml
│       ├── agent.cordis.yml
│       └── SKILL.md
├── skills/
│   ├── <Proyecto>-auditor/
│   ├── <Proyecto>-continuous-repair/
│   ├── <composed-skills-or-overrides>/
│   └── <project-specific-extensions-only-if-catalog-does-not-apply>/
├── contracts/
├── references/
├── templates/
├── adapters/
├── acceptance-plan.json
└── generation-report.md
```

Outside `generated/`, the run keeps discovery/design/tests/validation/checkpoint/report/finish
as the architecture describes.

## Operational gate for modes and skills

Each mode `agent.cordis.yml` includes exactly the operational base needed:
`@deepseek-ai/dsh-persona`, `@deepseek-ai/dsh-tool-bash`,
`@deepseek-ai/dsh-tool-fs`, `@deepseek-ai/dsh-tool-fs-search`,
`@deepseek-ai/dsh-skill-filesystem`, `@deepseek-ai/dsh-tool-skill` and the first-party
guard `./anti-escalation.mjs`. The Host fails closed if a row is missing or if
subagent/delegation, workflow, web/network or plugin-manager appears. Each required
plugin appears only once, with no duplicate names or IDs, and any unrecognized YAML
invalidates the composition. Each `SKILL.md` under `generated/skills/<name>` and
`generated/modes/<name>` carries minimal YAML frontmatter with the exact `name: <name>`
and a non-empty `description`.

The transaction copies each complete skill — resources included — and each mode's
`SKILL.md` to `bundle/skills/<name>`. It rejects collisions, symlinks and non-regular
entries; it configures each skills provider with `includeDefaultRoots: false` and an
absolute `customSkillDirs` to the bundle root. The receipt preserves both preset IDs.

## Invariants

1. Creator only emits `GENERATED` or a block of its own; never `ACCEPTED`/`ACTIVE`.
2. Exactly two final modes, project-specific.
3. Project-specific skills only with recurring procedure, evidence, boundaries and test.
4. The profile stores variable data; skills store procedures.
5. Auditor without product writes.
6. The first-party persona loads the exact skill first and, together with the lifecycle,
   forbids `sandbox_permissions`/`justification` for all values; a denial or a schema
   error becomes `RETAINED` without retry. The scoped guard rejects it before approval.
   Auditor persists state with strict schemas/caps; Repair derives the candidate by full
   base+IDs digest, applies closed checks and canonical invariants, and changes code only
   by bash with the candidate workdir. A simple prompt does not authorize commit: it
   leaves a dirty tree or a patch (`candidate_commit` nullable). It never uses
   write/edit on the product, merges, pushes or publishes. Concurrency/CAS and mechanical
   confinement remain pending proof and implementation.
7. QA and the later Auditor are observable.
8. A maximum of two attempts per unit.
9. No implicit publication/network/installation.
10. No new providers/models/routing.
11. Every operational value/decision has a source (`value sourcing`).
12. Load-bearing unknowns block the affected generation.
13. The Host, validators, tests, holdouts, capabilities and acceptance are not modified.
14. No maintainer paths/identities/secrets.

## Progressive disclosure

Skills use a small `SKILL.md` as router and load it under an explicit condition:

```text
modes/
internal/
references/
templates/
adapters/
```

The manifest declares the graph and hot paths. The Host validates references, cycles,
orphans, per-file/per-path budgets and contractual blocks.

## Per-skill contract

Each skill/mode declares:

- purpose/triggers/anti-triggers;
- inputs and sources;
- reads/writes;
- required/forbidden capabilities;
- invariants/anti-goals;
- state machine;
- handoffs;
- failure modes/retries/timeouts;
- rollback/migration;
- `SR-N` requirements;
- scenarios/stop conditions/evidence;
- provenance/license.

## Scenarios and holdouts

Creator generates public scenarios and holdout families. The Host materializes/hides
concrete cases. Tests/rubrics/thresholds/allowlists are read-only for the generator and
the repairer.

## Self review and handoff

Creator produces informative self-review and then invokes:

```bash
python3 -B scripts/bootstrap.py accept \
  --workspace <workspace> \
  --generated <creator-runs/generation-id/generated>
```

This command only requests validation. Creator does not install. The Host verifies
schema, manifest/hashes, capabilities/routing, graph/hot paths, security, provenance,
backup and functional acceptance.

## Backup and replacement

- identical: do not write;
- new: exclusive creation;
- managed/modified: full verified backup before touching the destination;
- foreign/local edit: `RETAINED` conflict;
- activation of the modes+skills set as a unit;
- failure: verified rollback;
- unverifiable rollback: `RECOVERY_REQUIRED`.

## Host acceptance

The Host runs:

1. static/schema/graph/portability;
2. exact load/origin/body;
3. public scenarios;
4. holdouts;
5. independent review/explicit degradation;
6. read/evidence/write denial;
7. red→green repair in candidate;
8. QA;
9. semantic re-audit;
10. persistence/reopen;
11. rollback/uninstall;
12. post-promotion smoke.

States:

```text
GENERATED → VALIDATING → BACKED_UP → STAGED → ACCEPTING → ACTIVE
                                       └→ RETAINED → ROLLED_BACK
                                                      └→ RECOVERY_REQUIRED
```

## External provenance restrictions

Patterns adapted from `jsmastery-pro/skills` commit `43b69e4` (MIT):
scope/audit/architect/develop/check/test/debug/document/sync, progressive disclosure and
hot-path budgets. Their final modes, slash workflow, npx/MCP auto-install,
Claude/web/Git dependencies and non-functional editorial rules are not copied. Substantial
copying requires the MIT notice and `THIRD_PARTY_NOTICES.md`.

## Acceptance of this contract

This document describes the contract implemented in C0–C5 and verified against real
packages in C2–C3 and clean-room pilots C6–C7. The verified state per stage is in
`PLAN_IMPLEMENTACION.md` and `docs/status.md`; the current gates and suite verifications
are in `tests/`.

---

## Shared terms

Terms shared by this canonical document and its Spanish translation, kept bilingual on
purpose: they are the vocabulary the tests of this repository assert on, so a reader of
either copy sees the same contract.

| Term | Meaning | Where it appears |
|---|---|---|
| `fuera del árbol canónico` | outside the canonical tree: the legacy two-file composition is not part of this contract | Opening section |
| `biblioteca base inmutable` | immutable base library: adapted, never rewritten or replaced | Skill selection strategy |
| `catálogo especializado` / specialized pattern catalog | `library/catalog`: specialized patterns that must be exhausted before an extension | Skill selection strategy |
| `extensión específica generada` / generated project-specific extension | the extension only justified when the layers below do not apply | Skill selection strategy |
| `<Proyecto>-auditor` | project-specific Auditor mode (never installed, never self-approved) | Required output, Invariants |
| `<Proyecto>-continuous-repair` | project-specific continuous-repair mode | Required output, Invariants |
| `value sourcing` | every operational value/decision declares its source | Invariants |
| `GENERATED` | the only terminal verdict Creator itself may emit | Invariants, Host acceptance |
| `RETAINED` | retained verdict, never overwritten, with evidence preserved | Invariants, Host acceptance |
| `fail-closed` (`falla cerrado`) | the Host refuses a package that is missing a required row | Operational gate |
| `run.json` | the run record: snapshot, inventory and lifecycle references | Host entry |
| `worktree` | sandboxed product worktree: no longer used; the Host provisions a shadow repository | Host entry, Invariants |
| `read-only` | mounting of product/framework and of tests, rubrics and thresholds | Host entry, Scenarios and holdouts |
| `preset.yml` / `mode.json` / `agent.cordis.yml` | the three artifacts every final mode declares | Required output |
| `SR-N` | scenario/stop-condition numbering the contract requires per skill | Per-skill contract |
