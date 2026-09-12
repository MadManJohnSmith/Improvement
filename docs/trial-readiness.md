# Preparación para prueba completa

**Estado actual:** operación v0.1 acotada; no autonomía Host.
**Uso:** checklist previo a una misión real de Auditor o Reparación continua.
**Fuente:** arquitectura vigente y `PLAN_IMPLEMENTACION.md`.

Este runbook es una lista de gates, no un diario ni un plan alternativo. Registrar la evidencia de ejecución en el workspace externo, no aquí.

## Estados

`HECHO` = evidencia suficiente y vigente; `PARCIAL` = mecanismo limitado; `PENDIENTE` = sin evidencia; `BLOQUEADO` = decisión/permisos/capacidad faltante; `RETAINED` = candidato preservado sin aceptación; `UNVERIFIED` = evidencia necesaria ausente.

## Gates

| Gate | Criterio | Evidencia recuperable | Resultado / estado | Bloqueo o siguiente acción |
|---|---|---|---|---|
| Identidad | Framework, producto y workspace externos identificados; revisión/base fijadas | `project.json`, `PROJECT.md`, Git externo | Registrar antes de actuar | Detener ante origen ambiguo |
| Skills | Origen, revisión, descubrimiento, cuerpo y ejecución nativa comprobados | Recibo externo y prueba de carga | `PARCIAL` en v0.1 | No confundir lectura con carga |
| Onboarding | Perfil externo, copias idempotentes, enlaces propios y conflictos rechazados | `onboard.py`, tests y workspace | `HECHO` mecánico | Permisos efectivos se comprueban aparte |
| Misión | Objetivo, autorización, base, rutas, exclusiones, criterios, límites y parada definidos | `task.json` y referencia real al encargo | Obligatorio | JSON no crea autorización |
| Reparación | `files`, `base` y `change_scope` completos; un escritor y candidato externo | `task.json`, snapshot y diff | Obligatorio | Fuera de scope ⇒ `RETAINED` |
| Validación | `argv` exacto, `shell=false`, timeout, salida externa y terminación comprobada | `check.json`, stdout/stderr | `PARCIAL` mecánico | Estado incierto ⇒ no reintentar a ciegas |
| QA | Revisor distinto, candidato/check/hash exactos y revisión suficiente | `qa.json` y referencia de sesión | Necesario en alto impacto | Ausencia ⇒ `UNVERIFIED`/`RETAINED` |
| Reauditoría | Candidato vigente, prueba íntegra y revisión semántica dirigida | recibo `reaudit` + informe Auditor/QA | Mecánica `PENDING_SEMANTIC_REVIEW` | No equivale a aceptación |
| Entrega | Recibo completo/parcial, referencias y hashes verificables | recibos externos y handoff | `PARCIAL` local | Handoff Host pendiente |
| Integración | Autorización separada, destino y diff revisados | decisión humana y registro externo | Pendiente por defecto | No integrar automáticamente |
| Recuperación | Timeout/cancelación/crash/reinicio reconciliados antes de otro escritor | pruebas de fallo específicas | Pendiente | Intervención supervisada |
| Capability | Lectura de producto, ejecución de framework y escritura externa concedidas una vez y reutilizables | recibo nativo y capability externa | `UNVERIFIED` si el Host no lo demuestra | No escalar a acceso total; retener |
| Auditoría completa | Inventario, unidades, delegación, consolidación y cola externa cerrados | `audit-manifest`, matriz, informe y `repair-queue` | Obligatorio para auditoría global | Sin siguiente prompt manual |
| Artefactos | Estado activo compacto; detalle histórico indexado por ciclo | `active/`, `cycles/`, `archive/`, hashes | Obligatorio | No cargar históricos completos |
| Privacidad | Sin credenciales/datos personales; worktree/HOME/XDG/symlink no son sandbox | inspección de rutas y permisos | Obligatorio | Detener si no se puede limitar |

## Preflight mínimo

1. Confirmar árbol del framework y producto; no mezclar repositorios.
2. Crear un `cycle_id` externo nuevo y escribir `started.json` antes de trabajar.
3. Ejecutar onboarding en workspace externo; repetir en dry-run/idempotencia.
4. Registrar revisión de skills y capacidades realmente observadas.
5. Para Auditoría completa, crear inventario, unidades, base, criterios, exclusiones y DAG antes de delegar.
6. Crear una unidad de reparación con `task.json`, base, criterios, exclusiones y `change_scope` si aplica.
7. Inspeccionar scripts, destinos, enlaces y dependencias antes de ejecutar.
8. Preparar candidato y evidencia fuera de framework/producto.
9. Ejecutar rojo/verde solo con comandos autorizados.
10. Solicitar QA independiente real cuando el riesgo lo exige.
11. Ejecutar `verify` y `reaudit`; conservar `UNVERIFIED` si falta evidencia.
12. Actualizar cola/ciclo y archivar detalle sin saturar el estado activo.
13. Integrar o publicar solo con autorización separada.

## Paradas obligatorias

Detener y devolver una excepción concreta ante: fuente inaccesible o ambigua, permisos insuficientes, candidato obsoleto, cambio fuera de alcance, QA ausente, prueba alterada, timeout/estado incierto, causa repetida sin evidencia nueva, datos sensibles no autorizados o solicitud de integrar/publicar sin decisión.

La prueba sintética del framework cubre mecanismos locales de ambos modos, pero no acredita producto real, IPC Tauri, QA independiente efectiva, autenticidad de actores, sandbox OS, recuperación durable, autonomía Host, coste medido ni transferencia a un segundo proyecto.
