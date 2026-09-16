# Preparación para pruebas: MVP comprobado y arquitectura 3.0

**Estado vigente:** arquitectura 3.0 aprobada; base MVP comprobada; flujo final de un comando pendiente C0–C7.
**Uso:** checklist para no confundir fixtures/MVP con la experiencia final del piloto.
**Fuente:** `ARQUITECTURA_FLUJO_AGENTES.md`, `PLAN_IMPLEMENTACION.md`, `docs/status.md`.

Este runbook no es un plan alternativo. Evidencia de ejecución va al workspace externo.

## A. Gates del MVP comprobado (fixtures/mantenimiento)

| Gate | Criterio | Estado vigente |
|---|---|---|
| Identidad | Framework/producto/workspace/base fijados | HECHO en MVP |
| Skills | Origen/cuerpo/carga nativa comprobados | HECHO en fixtures |
| Onboarding | Perfil/copias/enlaces/conflictos/idempotencia | HECHO mecánico |
| Misión | Objetivo/autoridad/base/criterios/límites | HECHO por contrato v1 |
| Reparación | candidato externo, change_scope, un escritor | HECHO |
| QA/reauditoría | actor/candidato/prueba/evidencia | HECHO con retenciones honestas |
| Controlador/recuperación | presupuesto/locks/reconciliación/crash de contenedor | HECHO con límites explícitos |
| Archivo | ciclos y manifests restaurables | HECHO |

Estos gates no acreditan bootstrap Creator 3.0 ni modos generados para terceros.

## B. Gates previos a pilotos con usuarios reales (C0–C7)

| Gate | Criterio | Estado |
|---|---|---|
| C0 schemas/fixtures | generation manifest, contracts, graph, scenarios, handoffs, drift; corpus positivo/negativo | PENDIENTE |
| C1 install | un comando prepara run/snapshot/authority sin modificar producto/config global | PENDIENTE |
| C2 Creator automático | RPC local, proveedor ya configurado, generación específica, manifest/finish | PENDIENTE |
| C3 Host validator | hashes/paths/capabilities/routing/contracts/graph/hot paths/licencias fail-closed | PENDIENTE |
| C4 transacción | backup completo, staging de conjunto, swap/rollback, update/uninstall | PENDIENTE |
| C5 acceptance | public scenarios, holdouts Host, verify/review, RETAINED repair, post-promotion smoke | PENDIENTE |
| C6 clean-room | dos proyectos nuevos, usuario sin contexto privado, install/update/uninstall | PENDIENTE |
| C7 distribución | licencia/avisos, tag, guía, feedback, clon reproducible | PENDIENTE |

## Preflight del piloto final

1. DSH compatible, Creator y proveedor/modelo ya configurados.
2. Clon del tag de piloto.
3. Proyecto fuera del framework y workspace externo.
4. Un único `bootstrap install`.
5. Cero copia manual de prompts/JSON/receipts.
6. Modos generados `<Proyecto>-auditor` y `<Proyecto>-continuous-repair`.
7. Skills específicas justificadas, no presets universales.
8. Creator invoca `accept`; Host decide.
9. Backups verificados antes de reemplazo.
10. Aceptación automática real y rollback probado.
11. Update por drift y uninstall conservador.
12. Registro de interacciones/feedback sin secretos.

## Paradas obligatorias

`RETAINED` ante proveedor/Creator/capability ausente, raíz ambigua, unknown load-bearing, skill ajena/local edit, ruta/hash inválido, routing cambiado, backup fallido, acceptance sin evidencia, reviewer no observable, rollback no verificable o publicación no autorizada.

No entregar el enlace como experiencia final de un comando mientras C0–C7 no estén HECHO.
