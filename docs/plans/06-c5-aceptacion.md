# Plan 06 — C5: aceptación automática DSH

**Salida:** `bootstrap accept` evalúa un candidato sin que Creator se autoapruebe.
**Precondiciones:** C0–C4.

## Escenarios obligatorios

- descubrimiento de los dos modos;
- carga nativa/origen/cuerpo exactos;
- lectura dirigida;
- evidencia externa;
- Auditor sin escritura de producto;
- reparación en candidato;
- rojo→verde;
- QA por actor/sesión observable;
- reauditoría semántica;
- reapertura/checkpoint;
- rollback/uninstall;
- routing/config global inalterados.

## Controles

- fixtures públicos separados de holdouts Host;
- tests/rúbricas/thresholds read-only;
- review separada de Creator;
- `verify` mecánico más juicio semántico explícito;
- ausencia de aislamiento → `DEGRADED_REVIEW`, no independencia;
- falta de evidencia → `UNVERIFIED/RETAINED`;
- repair vuelve siempre a Host evaluation;
- digest exacto de candidato/contrato.

## Salida

`host-verdict.json`, `evidence-ledger.jsonl`, `acceptance-record.json`, `retention-bundle` si aplica, `rollback-record` si falla.

## Gate

Solo Host puede emitir `ACTIVE`. Todo fallo deja generación staged o rollback íntegro; ninguna aceptación declarativa de Creator cambia estado.

## Adaptación

El escenario mínimo puede crecer por proyecto, nunca reducir criterios inmutables. Los holdouts se regeneran cuando un repair los expone.
