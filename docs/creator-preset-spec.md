# Contrato generacional para DSH Creator

**Versión:** 1 (implementado en C0–C5; verificado sobre paquetes reales en C2–C3 y pilotos C6–C7)
**Arquitectura:** [ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) v3.0

El contrato vigente define una generación completa; cualquier composición anterior de dos archivos queda fuera del árbol canónico y solo existe en el historial Git. Creator debe generar un paquete completo y específico del proyecto bajo `creator-runs/<generation-id>/generated/`; nunca instala ni se autoaprueba.

## Entrada Host

Creator recibe referencias a:

- `run.json`, snapshot e inventario;
- project manifest e instructions index;
- authority y runtime capabilities;
- routing efectivo (sin credenciales);
- plantillas normativas;
- skills generales;
- contratos/schemas;
- presupuesto y stop conditions;
- directorio de staging único.

Producto/framework se montan read-only; escritura solo dentro del run. La configuración/proveedor ya existe en DSH. El framework no recibe API keys.

## Estrategia de selección de skills

Creator debe resolver cada necesidad en este orden:

```text
biblioteca base inmutable
→ catálogo de patrones especializados
→ composición de varias skills
→ override declarativo limitado
→ extensión específica generada
→ RETAINED si ninguna opción es aceptable
```

Una extensión nueva exige demostrar que las capas anteriores no aplican. Una skill transferida de otro proyecto debe pasar aceptación completa en el proyecto destino. Creator no puede modificar controles, holdouts, thresholds, capabilities, evaluador, Host ni acceptance.

## Capacidades internas

Creator compone internamente:

```text
project discovery          (audit)
project documenter         (document)
contract/risk mapper       (audit + architect)
capability partitioner     (scope)
capability designer        (architect)
scenario author            (test)
skill generator            (develop)
generation repair          (debug)
drift analyzer             (sync)
```

No son modos finales ni se instalan como presets.

## Salida obligatoria

```text
generated/
├── generation-manifest.json
├── project-manifest.json
├── capabilities.json
├── modes/
│   ├── <Proyecto>-auditor/
│   └── <Proyecto>-continuous-repair/
├── skills/
│   ├── <Proyecto>-auditor/
│   ├── <Proyecto>-continuous-repair/
│   ├── <skills-compuestas-o-overrides>/
│   └── <extensiones-específicas-solo-si-no-aplica-catálogo>/
├── contracts/
├── references/
├── templates/
├── adapters/
├── acceptance-plan.json
└── generation-report.md
```

Fuera de `generated/`, el run conserva discovery/design/tests/validation/checkpoint/report/finish según la arquitectura.

## Invariantes

1. Creator solo emite `GENERATED` o un bloqueo propio; nunca `ACCEPTED`/`ACTIVE`.
2. Exactamente dos modos finales, específicos del proyecto.
3. Skills específicas solo con procedimiento recurrente, evidencia, fronteras y prueba.
4. Perfil guarda datos variables; skills guardan procedimientos.
5. Auditor sin escritura del producto.
6. Reparación solo en candidato/rama autorizada.
7. QA y Auditor posterior observables.
8. Máximo dos intentos por unidad.
9. Sin publicación/red/instalación implícitas.
10. Sin proveedores/modelos/routing nuevos.
11. Todo valor/decisión operativo tiene fuente (`value sourcing`).
12. Unknowns load-bearing bloquean la generación afectada.
13. No se modifican Host, validadores, tests, holdouts, capabilities ni acceptance.
14. No rutas/identidades/secretos del mantenedor.

## Progressive disclosure

Las skills usan `SKILL.md` pequeño como router y cargan bajo condición explícita:

```text
modes/
internal/
references/
templates/
adapters/
```

El manifest declara grafo y hot paths. El Host valida referencias, ciclos, huérfanos, presupuestos por archivo/ruta y blocks contractuales.

## Contrato por skill

Cada skill/mode declara:

- purpose/triggers/anti-triggers;
- inputs y fuentes;
- reads/writes;
- capabilities requeridas/prohibidas;
- invariantes/anti-goals;
- state machine;
- handoffs;
- failure modes/retries/timeouts;
- rollback/migración;
- requisitos `SR-N`;
- escenarios/stop conditions/evidencia;
- procedencia/licencia.

## Escenarios y holdouts

Creator genera escenarios públicos y familias de holdout. El Host materializa/oculta casos concretos. Tests/rúbricas/thresholds/allowlists son read-only para generador y reparador.

## Self review y handoff

Creator produce self-review informativa y luego invoca:

```bash
python3 -B scripts/bootstrap.py accept \
  --workspace <workspace> \
  --generated <creator-runs/generation-id/generated>
```

Este comando solo solicita validación. Creator no instala. El Host verifica schema, manifest/hashes, capabilities/routing, graph/hot paths, seguridad, procedencia, backup y aceptación funcional.

## Backup y reemplazo

- idéntico: no escribir;
- nuevo: creación exclusiva;
- gestionado/modificado: backup completo verificado antes de tocar destino;
- ajeno/local edit: conflicto `RETAINED`;
- activación del conjunto modos+skills como unidad;
- fallo: rollback verificado;
- rollback no verificable: `RECOVERY_REQUIRED`.

## Aceptación Host

El Host ejecuta:

1. static/schema/graph/portability;
2. carga/origen/body exactos;
3. escenarios públicos;
4. holdouts;
5. review independiente/degradada explícita;
6. read/evidence/write denial;
7. repair rojo→verde en candidato;
8. QA;
9. reauditoría semántica;
10. persistencia/reapertura;
11. rollback/uninstall;
12. post-promotion smoke.

Estados:

```text
GENERATED → VALIDATING → BACKED_UP → STAGED → ACCEPTING → ACTIVE
                                       └→ RETAINED → ROLLED_BACK
                                                      └→ RECOVERY_REQUIRED
```

## Restricciones de procedencia externa

Se adaptan patrones de `jsmastery-pro/skills` commit `43b69e4` (MIT): scope/audit/architect/develop/check/test/debug/document/sync, progressive disclosure y hot-path budgets. No se copian sus modos finales, slash workflow, npx/MCP auto-install, dependencias Claude/web/Git ni reglas editoriales no funcionales. Copia sustancial exige aviso MIT y `THIRD_PARTY_NOTICES.md`.

## Aceptación de este contrato

Este documento describe el contrato implementado en C0–C5 y verificado sobre paquetes reales en C2–C3 y pilotos clean-room C6–C7. El estado comprobado por etapa está en `PLAN_IMPLEMENTACION.md` y `docs/status.md`; los gates vigentes y las verificaciones de la suite en `tests/`.
