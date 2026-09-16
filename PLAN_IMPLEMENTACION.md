# Plan de implementación y progreso

**Estado:** arquitectura 3.0 aprobada; MVP operativo anterior aceptado; nueva capa de distribución/generación por proyecto pendiente de C0–C7.
**Actualización:** 2026-09-16
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md) v3.0

Este archivo es el único índice de progreso. Conserva dos niveles:

1. **Base MVP comprobada:** capacidades ya demostradas con DSH real, Syncify y RehabWeb.
2. **C0–C7:** implementación pendiente del flujo final de un comando: bootstrap → Creator automático → modos/skills específicos → validación/backup/aceptación Host → activación/rollback.

Los detalles históricos están en `CHANGELOG.md`; la evidencia privada, candidatos, sesiones y logs permanecen fuera del repositorio. Ningún documento o estado generado acredita por sí mismo ejecución.

## Estados

- `HECHO`: salida y gate comprobados con evidencia recuperable.
- `PARCIAL`: mecanismo o ensayo limitado; falta parte del gate.
- `PENDIENTE`: no implementado o sin evidencia suficiente.
- `BLOQUEADO`: requiere decisión, permiso o capacidad externa.
- `RETENIDO`: candidato preservado, pero no aceptado.

## Base MVP comprobada

| ID | Resultado | Estado | Evidencia principal | Límite conservado |
|---|---|---|---|---|
| B0 | Onboarding, skills, Host aislado y canal DSH | HECHO | `scripts/onboard.py`, `host_launcher.py`, `inference_channel.py`, presets fixture, tests; `docs/status.md` | No equivale al bootstrap Creator 3.0 |
| B1 | Auditoría, reparación, QA y reauditoría reales | HECHO | ciclos Syncify/RehabWeb; `missions.py`, `publisher.py`; ramas `workflow-repairs` | Unidades de producto RETAINED no se presentan como reparadas |
| B2 | Controlador, presupuesto, memoria y métricas | HECHO | `host_controller.py`, `budget.py`, `decisions.py`, `metrics.py` y regresiones | Descendientes remotos/pérdida física de energía limitados |
| B3 | Plugin de escritura y distribución privada por red | HECHO | `workflow-write`, clean-room remoto, regresiones | Plugin necesita empaquetado portable en C4 |
| B4 | MVP del núcleo fail-closed en dos proyectos | HECHO | 17/17 unidades con estado, archivos restaurables, `docs/status.md` | Acepta el framework, no declara productos libres de defectos |

## Etapas vigentes C0–C7

| ID | Resultado de salida | Estado | Trabajo principal | Gate de salida |
|---|---|---|---|---|
| C0 | Contratos generacionales y fixtures | PENDIENTE | Schemas de run/manifest/project/capabilities/modes/skills/tests/handoffs/drift; fixtures válidos/inválidos; ejemplos Syncify/RehabWeb saneados; procedencia MIT | Validador procesa corpus positivo/negativo sin tocar DSH ni destinos activos |
| C1 | `bootstrap install` determinista | PENDIENTE | Preflight DSH/proveedor/Creator; workspace; generation-id; snapshot/authority; skills generales; prompt/paquete Creator; checkpoint/reanudación | Clone limpio prepara run completo sin modificar producto/config global |
| C2 | Automatización DSH Creator | PENDIENTE | Cliente local autenticado; sesión Creator; pipeline interno scope/audit/architect/document/test/develop; presupuesto/timeout; manifest/finish obligatorios | Un comando genera paquete específico válido sin copiar prompts ni secretos |
| C3 | Validador Host de generación | PENDIENTE | Schema, manifest exhaustivo, paths/hashes, capabilities/routing, contratos, grafo, portabilidad, hot paths, scripts, licencias, anti-autoaprobación | Corpus negativo falla cerrado antes de cualquier backup/escritura activa |
| C4 | Backups, instalación transaccional y desinstalación | PENDIENTE | Ownership manifest; backup completo/verificado; staging generacional; swap; rollback; update; uninstall/purge separados; plugin portable | Fallos inyectados nunca dejan conjunto mixto; estado anterior restaurable |
| C5 | Aceptación automática DSH | PENDIENTE | Escenarios públicos + holdouts Host; verify/review; repair RETAINED con debug; load/read/evidence/repair/QA/reaudit/reopen/rollback | Creator invoca `accept`; solo Host emite ACTIVE o RETAINED/rollback |
| C6 | Piloto clean-room en proyectos nuevos | PENDIENTE | Proyecto Python/backend y proyecto multiparte; usuario sin contexto privado; install/update/uninstall; medir intervenciones/feedback | Usuario con DSH/proveedor configurado obtiene modos específicos con un comando |
| C7 | Promoción y distribución de piloto | PENDIENTE | Reconciliar resultados; docs/CI; licencia/THIRD_PARTY_NOTICES; tag; guía/feedback | Repo enlazable para testers, versión fijada y clean-room repetible |

## Dependencias

```text
C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7
          └──── discovery/design/test/generation internos ────┘
```

C0 puede preparar fixtures, schema y validadores en paralelo. C4 puede diseñarse mientras C2 avanza, pero no se acepta hasta que C3 valide un paquete real. C6 debe arrancar desde clon y DSH con proveedor ya configurado, no desde imagen preconfigurada.

## Capacidades internas de Creator

No son modos finales del usuario:

```text
creator-project-discovery          (audit)
creator-project-documenter         (document)
creator-contract-and-risk-mapper   (audit + architect)
creator-capability-partitioner     (scope)
creator-capability-designer        (architect)
creator-scenario-author            (test)
creator-skill-generator            (develop)
creator-generation-repair          (debug)
creator-drift-analyzer             (sync)
```

El resultado final por proyecto sigue siendo:

```text
<Proyecto>-auditor
<Proyecto>-continuous-repair
+ skills específicas justificadas
```

## Reglas de actualización

1. Solo se marca `HECHO` con evidencia recuperable y negativos pertinentes.
2. Un cambio material de diseño actualiza primero `ARQUITECTURA_FLUJO_AGENTES.md`.
3. No importar perfiles, candidatos, rutas privadas, sesiones o logs al repo.
4. Creator nunca puede cerrar su propia etapa como aceptada.
5. Backup presente no equivale a rollback comprobado.
6. Schema válido no equivale a skill útil ni segura.
7. El historial de C0–C7 va en Git/CHANGELOG, no como diario en la arquitectura.
