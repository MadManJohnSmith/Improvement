# Plan de implementación y progreso

**Estado:** hoja de ruta de destino; el estado de cada etapa debe respaldarse con evidencia recuperable.
**Actualización:** 2026-09-13
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md)

Guía de ejecución para el agente implementador: [Plan de cierre integral](docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md). Define trabajo y aceptación pendientes, no acredita su implementación ni sustituye los estados de esta matriz.

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
| 1 | Inventario dirigido, base y límites de pruebas | PARCIAL | `scripts/audit.py inventory`, snapshot SHA-256 y partición revalidada; `tests/test_audit_coverage.py`; perfiles/recibos externos | Demostrar revisión por perspectivas y cobertura semántica; la partición exhaustiva no la acredita |
| 2 | Publicador restringido con identidad, autorización, idempotencia y recuperación | PARCIAL | `scripts/publisher.py`, `tests/test_publisher.py`; primitive local con resolución en proceso nuevo; cortes en puntos de transición con reanudación idempotente en `tests/test_recovery_durable.py` | Adaptador Host, autenticidad fuerte y durabilidad ante pérdida de energía |
| 3 | Fixture contractual roja→verde con aceptación acotada | PARCIAL | `tests/test_operational_cycle.py`, `tests/test_two_mode_cycle.py`; seis candidatos RehabWeb con respuestas originales de QA en sesiones distintas | QA de alcance limitado: principalmente pruebas estáticas/configuración; no QA funcional general ni separación por rol impuesta por runtime |
| 4 | Handoff determinista Auditor→Reparación | PARCIAL | Lotes locales + estados `executor/qa/auditor` con `actor_id` distinto por rol; `bind_role()` declara roles técnicos y aceptación bloqueada sin QA `VERIFIED` y artefactos vigentes vía `missions.verify`; handoff solo `COMPLETE` | Autorización Host multi-actor, independencia real y autenticidad |
| 5 | Piloto real de una unidad de producto | PARCIAL | Nueve cierres Syncify agrupan 73 hallazgos; seis cierres RehabWeb con rojo/verde, QA original en sesiones distintas y hashes de recibos coherentes; candidatos externos separados | QA Syncify parcialmente documental; reauditorías RehabWeb `PENDING_SEMANTIC_REVIEW`; sin integración conjunta ni producto. Recibos no revalidados contra todos los candidatos en la revisión de estado |
| 6 | Flujo habitual con coste y calidad comparables | PARCIAL | `scripts/audit.py`, capability local y archivo compacto; resúmenes RehabWeb registran 73 y 218 requests en lotes distintos, el segundo incluye 13 denegadas; no son coste total ni requests productivas | Métricas finas comparables de campo, memoria de decisiones, validación de evidencia humana/prevención y consumo de cola completa en una sesión |
| 7 | Controlador Host y recuperación ante fallos | PARCIAL | `tests/test_recovery_durable.py` sobre fixtures: operación continuada con presupuesto durable (`scripts/budget.py`), reconciliación en durante QA/antes de publicar/después de publicar, timeout/cancelación/caída de worker/reinicio launcher, descendientes locales terminados | Controlador Host real; autonomía LLM; descendientes remotos y concurrencia hostil |
| 8 | Transferencia a un segundo proyecto | PARCIAL | RehabWeb: partición de 381 archivos y seis reparaciones con QA limitada en candidatos separados; carga de skills verificada en sondas, no ligada a esas misiones | Completar/reconciliar cola (44 ready declarados), revisión semántica pendiente, carga/aplicación nativa en misión real y aceptación integral |

## Regla de actualización

Una misión actualiza únicamente la fila afectada: estado, enlace a evidencia externa, bloqueo y siguiente salida. No añadir narración de sesión, logs, candidatos ni datos privados. Un cambio material de alcance o contrato actualiza primero la arquitectura y después esta tabla.
