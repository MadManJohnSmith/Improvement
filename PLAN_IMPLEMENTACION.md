# Plan de implementación y progreso

**Estado:** hoja de ruta de destino; el estado de cada etapa debe respaldarse con evidencia recuperable.
**Actualización:** 2026-09-10
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md)

Este archivo es un índice compacto, no un diario. Cada etapa conserva solo estado, evidencia principal, bloqueo y siguiente salida. Los detalles históricos van en `CHANGELOG.md`; los artefactos de ejecución permanecen fuera del repositorio. La auditoría completa usa ciclos externos versionados, cola activa compacta y archivo indexado; no importa historiales completos en el estado vigente.

## Estados

- `HECHO`: salida y criterio comprobados.
- `PARCIAL`: mecanismo o ensayo limitado; falta parte del criterio.
- `PENDIENTE`: aún no implementado o sin evidencia suficiente.
- `BLOQUEADO`: requiere decisión, permiso o capacidad externa.
- `RETENIDO`: candidato preservado, pero no aceptado.

## Etapas

| ID | Resultado de salida | Estado | Evidencia principal | Bloqueo / siguiente salida |
|---|---|---|---|---|
| 0 | Herramientas y capacidades observadas sin bucles inválidos | PARCIAL | `docs/status.md`; `scripts/host_launcher.py` fail-closed con servicios reales y `scripts/inference_channel.py` acotado (`tests/test_host_launcher.py`, `tests/test_inference_channel.py`); presets externos con mapeo de modelos y denegación fail-closed (`tests/test_dsh_preset_mapping.py`) | Enforcement equivalente en el Host de producción (el launcher aislado es el rig); escenario conductual de escalada confirmado con LLM, corrección documentada |
| 1 | Inventario dirigido, base y límites de pruebas | PARCIAL | `docs/status.md`; perfiles y recibos externos | Completar inventario solo cuando una misión lo necesite |
| 2 | Publicador restringido con identidad, autorización, idempotencia y recuperación | PARCIAL | `scripts/publisher.py`, `tests/test_publisher.py`; primitive local con resolución en proceso nuevo; cortes en puntos de transición con reanudación idempotente en `tests/test_recovery_durable.py` | Adaptador Host, autenticidad fuerte y durabilidad ante pérdida de energía |
| 3 | Fixture contractual roja→verde con aceptación acotada | PARCIAL | `tests/test_operational_cycle.py`, `tests/test_two_mode_cycle.py`; QA semántica real con subagente independiente en recibos `qa.json` de RehabWeb (turnos LLM reales, sesiones separadas) | Escalar QA real a la cola completa; separación QA/ejecución sigue procedimental en runtime |
| 4 | Handoff determinista Auditor→Reparación | PARCIAL | Lotes locales + estados `executor/qa/auditor` con `actor_id` distinto por rol; `bind_role()` declara roles técnicos y aceptación bloqueada sin QA `VERIFIED` y artefactos vigentes vía `missions.verify`; handoff solo `COMPLETE` | Autorización Host multi-actor, independencia real y autenticidad |
| 5 | Piloto real de una unidad de producto | PARCIAL | Syncify 9/9 unidades `ACCEPTED` con `missions.verify` (`session-syncify/workspace/cycles/syncify-audit-001/repairs/`); RehabWeb 6 unidades `ACCEPTED` con rojo-verde real, QA subagente independiente y reauditoría (`session-rehabweb-2/cycles/rehabweb-audit-001/repairs/`); integración solo en copia de ensayo, producto intacto | Cola RehabWeb restante (44 ready); misión usuario-real íntegra requiere skills preparadas en el padre directo |
| 6 | Flujo habitual con coste y calidad comparables | PARCIAL | `scripts/audit.py`, capability local y archivo circular; lotes reales con presupuesto de requests observado y documentado por lanzamiento (169 y 218 productivas en RehabWeb) | Métricas comparables de campo y consumo de cola completa en una sesión |
| 7 | Controlador Host y recuperación ante fallos | PARCIAL | `tests/test_recovery_durable.py` sobre fixtures: operación continuada con presupuesto durable (`scripts/budget.py`), reconciliación en durante QA/antes de publicar/después de publicar, timeout/cancelación/caída de worker/reinicio launcher, descendientes locales terminados | Controlador Host real; autonomía LLM; descendientes remotos y concurrencia hostil |
| 8 | Transferencia a un segundo proyecto | PARCIAL | RehabWeb como segundo proyecto real: auditoría vigente + 6 reparaciones `ACCEPTED` reutilizando el flujo sin adaptarlo; onboarding de skills en preparación | Completar cola, carga nativa de skills en la instancia real y aceptación usuario-real |

## Regla de actualización

Una misión actualiza únicamente la fila afectada: estado, enlace a evidencia externa, bloqueo y siguiente salida. No añadir narración de sesión, logs, candidatos ni datos privados. Un cambio material de alcance o contrato actualiza primero la arquitectura y después esta tabla.
