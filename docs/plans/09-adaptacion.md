# Plan 09 — adaptation and learning protocol

**English** | [Español](09-adaptacion.es.md)

**Stage:** cross-cutting; mandatory before changing any plan in response to new evidence.
**Goal:** allow plans to adapt without becoming a parallel backlog or weakening the gates.

## Change classification

| Type | Example | Action |
|---|---|---|
| Environmental fact | DSH version, observed capability | record the source and adjust the precondition; do not redesign |
| Mechanical defect | invalid schema, race, incorrect hash | fix the responsible component + minimal regression |
| Material decision | new root, provider, data, publication | stop and ask the owner |
| Project drift | new architecture or commands | new discovery/contract; invalidate affected acceptance |
| Optional improvement | ergonomics, context, metric | `P2`, never a compensable gate |
| Contract change | states, permissions, criteria | update the architecture before code |

## Adaptation cycle

1. Detect the discrepancy.
2. Preserve external evidence and the exact base.
3. Classify the change.
4. Check whether it invalidates candidates/acceptances.
5. Propose the smallest change.
6. Record the decision and alternatives.
7. Update the architecture if the contract changes.
8. Update the plan, scripts and regression.
9. Run positive and negative cases.
10. Update status and changelog.

## Prohibitions

- do not edit framework instructions from a product mission;
- do not expand permissions to overcome a failure;
- do not treat frequency as quality;
- do not treat a model recommendation as authorization;
- do not move a retained item to accepted for lack of evidence;
- do not reuse acceptance with a different hash/base;
- do not delete a backup or uncertain state to appear clean;
- do not add a skill because an isolated finding suggests it without a recurring procedure.

## Creator and drift

Regeneration creates a new `creator-runs/<generation-id>`. The previous generation remains active until:

- the new discovery identifies material changes;
- contracts are recalculated;
- scenarios/holdouts are updated;
- Host validates and accepts;
- the backup is verified;
- swap and post-promotion smoke tests pass.

The absence of semantic changes produces `NO_OP`, not a rewrite.

## Adaptable closure

Skill selection is reconsidered only if the contract/base changes or new evidence appears. An extension must not replace a base merely for convenience (Spanish contract wording: “No se sustituye una base por una extensión por conveniencia”).

The plan is considered current only if:

- its references exist;
- its gates match the architecture;
- its commands do not point to personal paths;
- its negative cases still cover the risks;
- the index status matches the evidence.

If any condition fails, the plan remains `RETAINED` pending review.
