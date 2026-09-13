# Plan de implementación y progreso

**Estado:** MVP del núcleo aceptado el 2026-09-13; extensiones y límites restantes se respaldan por separado.
**Actualización:** 2026-09-13
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md)

Guías de ejecución para el agente implementador: [Plan de cierre integral](docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md) (ejecutado en su fase P0–P9 el 2026-09-13) y [Plan de pendientes del núcleo](docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md) (organiza lo restante: cola completa, reauditoría semántica, controlador Host, instrumentación, durabilidad y decisiones del titular). Ninguna de las dos acredita implementación ni sustituye los estados de esta matriz.

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
| 5 | Piloto real de una unidad de producto | HECHO | `docs/status.md` (hito 2026-09-13 misión de cierre): dos vueltas reales Syncify y una RehabWeb en copias aisladas con rig (launcher+canal+presets), rojo→verde real, QA subagente, verify/reaudit y lotes `syncify-u1b`/`syncify-u2b`/`rehabweb-u1b` COMPLETE con etapas | Consumo de cola completa por proyecto y reauditoría semántica posterior como turno propio de Auditor |
| 6 | Flujo habitual con coste y calidad comparables | HECHO | `scripts/metrics.py` implementado y cargado con datos reales (24 turnos, 684 requests, ~6,8 M tokens de entrada; digests verificados); `scripts/decisions.py` con 2 decisiones vigentes recuperables por unidad | Comparación contra baseline de igual alcance y controlador Host en misión real |
| 7 | Controlador Host y recuperación ante fallos | HECHO | `scripts/host_controller.py` (8 tests con fake) + suite de recuperación + **primera unidad real conducida por el controlador de punta a punta** (syncify-archive-security, lote syncify-u4) + caída real del rig | Misión multi-unidad completa conducida por el controlador; descendientes remotos y pérdida de energía |
| 8 | Transferencia a un segundo proyecto | HECHO | RehabWeb: dos vueltas completas (alertas: 403 a paciente; adaptaciones: autoriza el terapeuta responsable) con QA subagente, lotes `rehabweb-u1b`/`u2` COMPLETE y suite integrada 74 tests OK en copia del padre; archivo restaurable | Consumir la cola completa por proyecto y reauditoría semántica como turno propio |

## Regla de actualización

Una misión actualiza únicamente la fila afectada: estado, enlace a evidencia externa, bloqueo y siguiente salida. No añadir narración de sesión, logs, candidatos ni datos privados. Un cambio material de alcance o contrato actualiza primero la arquitectura y después esta tabla.
