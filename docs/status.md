# Estado comprobado del framework

**Actualización:** 2026-09-16
**Arquitectura vigente:** [v3.0](../ARQUITECTURA_FLUJO_AGENTES.md)
**Backlog único:** [C0–C7](../PLAN_IMPLEMENTACION.md)

Este documento registra únicamente el estado vigente. El detalle de iteraciones anteriores está en Git/`CHANGELOG.md`, no aquí.

## Base técnica comprobada

El repositorio conserva servicios Host y regresiones reutilizables:

- onboarding externo idempotente, manifest y enlaces gestionados;
- inventario/partición SHA-256 y cobertura fail-closed;
- contratos de misión, checks y verificación documental;
- publicador local idempotente y etapas de rol;
- presupuesto durable, decisiones y métricas append-only;
- controlador Host con locks/reconciliación/cancelación;
- launcher Linux aislado y canal de inferencia acotado;
- plugin de escritura con semántica de escalada corregida;
- QA, reauditoría semántica, archivo/restauración y crash de proceso/contenedor demostrados;
- distribución privada por red y clean-room del código base demostrada.

Estas capacidades constituyen la base MVP comprobada. No equivalen al flujo de incorporación 3.0 ni a modos finales para proyectos nuevos.

## Eliminaciones de vigencia

- No hay presets Auditor/Reparación genéricos en la distribución canónica.
- No hay skills operativas universales del MVP en el árbol actual.
- No hay planes P0–P9, M1–M8 ni diagramas v2.4 en la documentación vigente.
- Los nombres/configuraciones usados en proyectos de prueba no son defaults.
- El contrato Creator de dos archivos fue reemplazado por el paquete generacional completo.

El historial eliminado sigue disponible en Git y no debe reconstruirse como instrucciones actuales.

## Pendiente vigente — C0–C7

| Etapa | Estado | Salida requerida |
|---|---|---|
| C0 | PENDIENTE | schemas/fixtures/manifests/contracts/tests/handoffs/drift y procedencia |
| C1 | PENDIENTE | `bootstrap install` determinista y reanudable |
| C2 | PENDIENTE | llamada automática a DSH Creator y pipeline interno completo |
| C3 | PENDIENTE | validador Host fail-closed de generación |
| C4 | PENDIENTE | backups de conjunto, staging, swap, rollback, update/uninstall |
| C5 | PENDIENTE | aceptación automática con escenarios/holdouts/review/repair |
| C6 | PENDIENTE | pilotos clean-room en proyectos nuevos |
| C7 | PENDIENTE | licencia/avisos, tag, guía y distribución de piloto |

## Estrategia de skills aprobada

Creator selecciona primero la biblioteca base inmutable y el catálogo de patrones especializados; después compone o aplica overrides declarativos. Solo genera una extensión cuando demuestra que esas capas no aplican, con contrato, escenarios y aceptación específica. Una skill transferida no es válida automáticamente para otro proyecto. La regeneración no sustituye bases por conveniencia.

## Experiencia final objetivo

```text
usuario configura DSH/proveedor una vez
→ bootstrap install
→ Creator descubre/diseña/genera modos y skills específicos
→ Creator invoca accept
→ Host valida y respalda
→ aceptación automática
→ activación transaccional o rollback
→ usuario opera <Proyecto>-auditor y <Proyecto>-continuous-repair
```

## Límites vigentes

- `bootstrap.py` y C0–C7 aún no están implementados.
- No entregar todavía el repositorio como experiencia final de un comando.
- Licencia pública y `THIRD_PARTY_NOTICES.md` deben resolverse en C7.
- La pérdida física de energía y descendientes remotos hostiles no tienen garantía total.
- Configurar proveedor en DSH es responsabilidad previa del usuario; el framework no obtiene API keys.
