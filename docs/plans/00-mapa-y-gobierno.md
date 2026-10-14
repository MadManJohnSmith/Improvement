# Plan 00 — overall map and implementation governance

**English** | [Español](00-mapa-y-gobierno.es.md)

**Stage:** cross-cutting across C0–C7.
**Initial status:** PENDIENTE (pending).
**Objective:** implement architecture 3.0 gradually without conflating the normative design, existing mechanisms, trials, products or the owner's decisions.

## Layers

| Layer | Artifacts | Responsible party | Rule |
|---|---|---|---|
| Norm | `ARQUITECTURA_FLUJO_AGENTES.md` | owner/maintainer | One current design, not a diary |
| Index | `PLAN_IMPLEMENTACION.md` | maintainer | Single backlog/status index |
| Plans | `docs/plans/*.md` | maintainer | Adaptable procedures, not status records |
| Code | `scripts/`, `skills/`, `tests/` | authorized maintenance | Permanent regressions |
| Runs | `creator-runs/`, receipts, logs | external workspace | Never in the canonical repository |
| Product | user repositories and branches | owner/product | Do not modify without explicit authorization |

## Conventions for each stage

Each stage creates an external run with:

```text
<external-run>/
├── started.json
├── mandate.json
├── baseline.json
├── budget/
├── inputs/
├── work/
├── evidence/
├── checkpoint.json
├── report.md
└── finish.json
```

`started.json` is written before inspection. `checkpoint.json` is updated at every gate. A blockage preserves `RETAINED` or `BLOCKED` and an exact next action.

## Budget and authority

Before each stage, set:

- maximum requests/tokens/time;
- maximum attempts per unit;
- readable and writable roots;
- permitted data;
- already-configured models/providers;
- whether network access is permitted;
- whether the product may be changed or only a branch/candidate;
- whether publication is permitted.

Permissions are not inferred from `AUTHORIZED` written by an agent, a manifest or a prompt.

## Cross-cutting gates

1. **Base immutability:** snapshot/hashes before a change.
2. **Isolation:** external workspace, no secrets, no global effects.
3. **Contract:** schemas and ownership defined before generation.
4. **Evidence:** every positive and negative case has a source and scope.
5. **Fail closed:** unknowns or missing capabilities retain the run.
6. **Idempotence:** repetition neither duplicates nor deletes others' work.
7. **Review:** the generating actor is not the only accepting actor.
8. **Rollback:** every reversible state change retains a backup.
9. **Update:** one index row, one changelog entry, one reviewed commit.

## Authorized adaptation

At startup, complete this externally:

```yaml
plan_revision: <commit o digest>
run_id: <opaco>
base_revision: <sha/manifest>
changes_to_steps: []
reason_for_changes: []
new_risks: []
open_decisions: []
```

A material contract adaptation requires changing architecture 3.0 first, then this plan.

## Recommended order

```text
C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7
         ├──────── C4 may be designed in parallel after C0
         └──────── C3 must validate real packages before C4/C5
```

C4 may be designed in parallel after C0; C3 must validate real packages before C4/C5. Do not start C6 with a preconfigured image: it must be tested from a clone and DSH with a configured provider.
