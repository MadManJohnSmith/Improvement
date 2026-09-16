# Diagramas Interactivos de Arquitectura y Flujo

Diagramas generados y validados con la skill `archify` (perfil `showcase`, validados en resoluciones de 1440×900 a 2048×1320 con Google Chrome headless).

**Estado:** estos diagramas representan el MVP/arquitectura v2.4 comprobada. La arquitectura normativa v3.0 añade `bootstrap → Creator → generación específica → accept Host → backup/transacción/rollback`; su actualización visual forma parte de C0/C7. Hasta entonces no interpretar los HTML como descripción completa de 3.0.

Cada archivo HTML es autónomo e interactivo: soporta temas claro/oscuro, zoom/pan, búsqueda de nodos, capítulos/vistas guiadas y exportación SVG/PNG/WebM.

## Índice de diagramas

| Tipo | Archivo fuente | Artefacto HTML entregado | Propósito |
|---|---|---|---|
| `architecture` | `flujo-arquitectura.architecture.json` | [`flujo-arquitectura.html`](flujo-arquitectura.html) | **Topología histórica y aislamiento:** límites entre Framework, Producto de fixture (Syncify), Workspace y Runner del MVP. |
| `workflow` | `flujo-operativo.workflow.json` | [`flujo-operativo.html`](flujo-operativo.html) | **Flujo operativo por etapas:** Onboarding → Auditoría acotada → Reparación en workspace → QA independiente → Cierre. |
| `sequence` | `secuencia-ejecucion.sequence.json` | [`secuencia-ejecucion.html`](secuencia-ejecucion.html) | **Secuencia de llamadas y herramientas:** intercambio entre Operador, DSH Agent, missions.py runner/verify, Workspace y QA subagent. |
| `lifecycle` | `ciclo-vida-unidad.lifecycle.json` | [`ciclo-vida-unidad.html`](ciclo-vida-unidad.html) | **Máquina de estados de la unidad:** transiciones entre PLANNED, AUTHORIZED, CANDIDATE, VERIFIED, ACCEPTED, RETAINED y UNVERIFIED. |
| `dataflow` | `flujo-datos-evidencia.dataflow.json` | [`flujo-datos-evidencia.html`](flujo-datos-evidencia.html) | **Cadena criptográfica de evidencia:** flujo de hashes SHA-256 desde task.json hasta check-base/ (rojo), check-1/ (verde), qa.json y result.json. |

## Validación y entrega

Para volver a validar o compilar los diagramas:

```bash
# Configura la ubicación de la skill archify y resuelve el repo actual.
export ARCHIFY_ROOT=/ruta/a/archify
export REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$ARCHIFY_ROOT"

for spec in \
  architecture:flujo-arquitectura.architecture.json \
  workflow:flujo-operativo.workflow.json \
  sequence:secuencia-ejecucion.sequence.json \
  lifecycle:ciclo-vida-unidad.lifecycle.json \
  dataflow:flujo-datos-evidencia.dataflow.json; do
  type="${spec%%:*}"
  file="${spec#*:}"
  node bin/archify.mjs validate "$type" "$REPO_ROOT/docs/diagrams/$file" --quality showcase --json
done

# Los deliver/visual-check se ejecutan de igual modo usando $REPO_ROOT.
```

No copies rutas del mantenedor. Los diagramas 3.0 deberán regenerarse en C0/C7 antes del piloto.
