# Architecture 3.0 implementation plans

**Status:** C0–C7 complete. These plans are kept as a record of the executed procedure and as an
adaptation template for future work; the current state lives in `PLAN_IMPLEMENTACION.md`
(including the post-C7 section) and `docs/status.md`.

**English** | [Español](README.es.md)

These documents decompose the approved architecture into adaptable iterations (`adaptables` in the original contract). They replace
neither `ARQUITECTURA_FLUJO_AGENTES.md` nor `PLAN_IMPLEMENTACION.md`:

- `ARQUITECTURA_FLUJO_AGENTES.md` is the norm.
- `PLAN_IMPLEMENTACION.md` is the single progress index.
- `docs/progreso-agentico.md` is the one-page view of every C/D/E/F/G/M/P/U milestone with its
  derived state; it does not replace the index.
- `docs/plans/` holds detailed procedures to execute each stage and update it without creating
  parallel backlogs.
- `docs/status.md` keeps the verified facts.

## Order

1. [00 — general map and implementation governance](00-mapa-y-gobierno.md)
2. [01 — C0: contracts, schemas and fixtures](01-c0-contratos-fixtures.md)
3. [02 — C1: deterministic bootstrap](02-c1-bootstrap.md)
4. [03 — C2: Creator automation](03-c2-creator.md)
5. [04 — C3: Host validator](04-c3-validador-host.md)
6. [05 — C4: transactional backup and install](05-c4-transaccion.md)
7. [06 — C5: automatic acceptance](06-c5-aceptacion.md)
8. [07 — C6: clean-room pilot](07-c6-piloto.md)
9. [08 — C7: promotion and distribution](08-c7-promocion.md)
10. [09 — adaptation and learning protocol](09-adaptacion.md)
11. [10 — public beta launch](10-lanzamiento-publico.md)
12. [11 — v0.1.0 beta notes](11-notas-beta-v0.1.0.md) — published 2026-09-30 with tag `v0.1.0-beta`
13. [System One decision channel](system-one-decision-channel.md) — the advisory channel for
    decision models, its phases and where it must never enter
14. [Project lifecycle modes](project-lifecycle-modes.md) — the candidate domains beyond
    audit, repair and implementation, their boundaries and what is still unproven

## How to use the plans

Each plan is an executable proposal, not a licence to skip authority. Before starting a stage:

1. read the architecture, the index and the stage plan;
2. check the preconditions still hold;
3. copy the plan to an external `run` with `run_id`, base, budget and owner;
4. adjust only the **Authorized adaptation** section and record the reason;
5. execute the steps in order, preserving foreign work;
6. verify the negatives before marking gates;
7. update only the row in `PLAN_IMPLEMENTACION.md` and `docs/status.md`;
8. record decisions and changes in `CHANGELOG.md`;
9. local commit only after reviewing the diff; publication is separate and explicit.

A plan may end `DONE`, `PARTIAL`, `RETAINED` or `BLOCKED`; it is never declared complete for
having run commands.
