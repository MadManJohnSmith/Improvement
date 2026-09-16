# Plan 00 — mapa general y gobierno de implementación

**Etapa:** transversal a C0–C7.
**Estado inicial:** PENDIENTE.
**Objetivo:** ejecutar la arquitectura 3.0 gradualmente sin mezclar diseño normativo, mecanismos existentes, ensayos, productos ni decisiones del titular.

## Capas

| Capa | Artefactos | Responsable | Regla |
|---|---|---|---|
| Norma | `ARQUITECTURA_FLUJO_AGENTES.md` | titular/mantenedor | Un diseño vigente, no diario |
| Índice | `PLAN_IMPLEMENTACION.md` | mantenedor | Único backlog/estado |
| Planes | `docs/plans/*.md` | mantenedor | Procedimientos adaptables, no estados |
| Código | `scripts/`, `skills/`, `tests/` | mantenimiento autorizado | Regresiones permanentes |
| Runs | `creator-runs/`, recibos, logs | workspace externo | Nunca en repo canónico |
| Producto | repos y ramas de usuario | titular/producto | No modificar salvo autorización explícita |

## Convenciones de cada etapa

Cada etapa crea un run externo con:

```text
<external-run>/
├── started.json
├── mandate.json
├── baseline.json
├── budget/
├── inputs/
├── work/
├── evidence/
├── checkpoint.json
├── report.md
└── finish.json
```

`started.json` se escribe antes de inspeccionar. `checkpoint.json` se actualiza en cada gate. Un bloqueo conserva `RETAINED` o `BLOCKED` y una siguiente acción exacta.

## Presupuesto y autoridad

Antes de cada etapa se fijan:

- requests/tokens/tiempo máximos;
- máximo de intentos por unidad;
- raíces legibles y escribibles;
- datos permitidos;
- modelos/proveedores ya configurados;
- si se permite red;
- si se permite cambiar producto o solo una rama/candidato;
- si se permite publicar.

No se deducen permisos de `AUTHORIZED` escrito por un agente, de un manifest o de un prompt.

## Gates transversales

1. **Inmutabilidad de base:** snapshot/hashes antes del cambio.
2. **Aislamiento:** workspace externo, sin secretos, sin efectos globales.
3. **Contrato:** schemas y ownership definidos antes de generación.
4. **Evidencia:** cada positivo y negativo tiene fuente y alcance.
5. **Fail-closed:** desconocido o capability ausente retiene.
6. **Idempotencia:** repetir no duplica ni borra trabajo ajeno.
7. **Revisión:** el actor que genera no es el único que acepta.
8. **Rollback:** todo cambio de estado reversible conserva backup.
9. **Actualización:** una fila del índice, una entrada de changelog, un commit revisado.

## Adaptación autorizada

Al iniciar, completar externamente:

```yaml
plan_revision: <commit o digest>
run_id: <opaco>
base_revision: <sha/manifest>
changes_to_steps: []
reason_for_changes: []
new_risks: []
open_decisions: []
```

Una adaptación material de contrato requiere primero cambiar arquitectura 3.0 y después este plan.

## Orden recomendado

```text
C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7
         ├──────── C4 puede diseñarse en paralelo después de C0
         └──────── C3 debe validar paquetes reales antes de C4/C5
```

No iniciar C6 con imagen preconfigurada: debe probarse desde clon y DSH con proveedor configurado.
