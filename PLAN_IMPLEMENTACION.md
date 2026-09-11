# Plan de implementación y progreso

**Estado:** hoja de ruta de destino; el estado de cada etapa debe respaldarse con evidencia recuperable.
**Actualización:** 2026-09-10
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md)

Este archivo es un índice compacto, no un diario. Cada etapa conserva solo estado, evidencia principal, bloqueo y siguiente salida. Los detalles históricos van en `CHANGELOG.md`; los artefactos de ejecución permanecen fuera del repositorio.

## Estados

- `HECHO`: salida y criterio comprobados.
- `PARCIAL`: mecanismo o ensayo limitado; falta parte del criterio.
- `PENDIENTE`: aún no implementado o sin evidencia suficiente.
- `BLOQUEADO`: requiere decisión, permiso o capacidad externa.
- `RETENIDO`: candidato preservado, pero no aceptado.

## Etapas

| ID | Resultado de salida | Estado | Evidencia principal | Bloqueo / siguiente salida |
|---|---|---|---|---|
| 0 | Herramientas y capacidades observadas sin bucles inválidos | PARCIAL | `docs/status.md`; regresiones DSH y validación local | Falta enforcement Host durable y validación de recuperación |
| 1 | Inventario dirigido, base y límites de pruebas | PARCIAL | `docs/status.md`; perfiles y recibos externos | Completar inventario solo cuando una misión lo necesite |
| 2 | Publicador restringido con identidad, autorización, idempotencia y recuperación | PARCIAL | `scripts/publisher.py`, `tests/test_publisher.py`; primitive local con resolución en proceso nuevo | Adaptador Host, autenticidad fuerte y pruebas de crash/durabilidad |
| 3 | Fixture contractual roja→verde con aceptación acotada | PARCIAL | `tests/test_operational_cycle.py`; fixtures externos | QA semántica real cuando el impacto lo requiera |
| 4 | Handoff determinista Auditor→Reparación | PARCIAL | Ensayo histórico supervisado externo | Resolución Host sin ayuda semántica del operador |
| 5 | Piloto real de una unidad de producto | RETENIDO | Candidatos externos queue/library; piloto histórico externo sin integración | QA/reauditoría/integración autorizadas según unidad vigente |
| 6 | Flujo habitual con coste y calidad comparables | PENDIENTE | Sin medición LLM de campo | Lote real autorizado y métricas comparables |
| 7 | Controlador Host y recuperación ante fallos | PENDIENTE | Diseño en arquitectura; sin prueba de campo | Intención/entrega/ack, unicidad, cancelación y reconciliación |
| 8 | Transferencia a un segundo proyecto | PENDIENTE | Sin piloto acreditado | Repetir ciclo con otro proyecto y conservar límites |

## Regla de actualización

Una misión actualiza únicamente la fila afectada: estado, enlace a evidencia externa, bloqueo y siguiente salida. No añadir narración de sesión, logs, candidatos ni datos privados. Un cambio material de alcance o contrato actualiza primero la arquitectura y después esta tabla.
