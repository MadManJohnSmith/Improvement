# Diagramas Interactivos de Arquitectura y Flujo

Diagramas generados y validados con la skill `archify` (perfil `showcase`, validados en resoluciones de 1440×900 a 2048×1320 con Google Chrome headless).

Cada archivo HTML es autónomo e interactivo: soporta temas claro/oscuro, zoom/pan, búsqueda de nodos, capítulos/vistas guiadas y exportación SVG/PNG/WebM.

## Índice de diagramas

| Tipo | Archivo fuente | Artefacto HTML entregado | Propósito |
|---|---|---|---|
| `architecture` | `flujo-arquitectura.architecture.json` | [`flujo-arquitectura.html`](flujo-arquitectura.html) | **Topología y aislamiento:** límites entre Framework canónico, Producto (Syncify), Workspace privado y Runner de misiones. |
| `workflow` | `flujo-operativo.workflow.json` | [`flujo-operativo.html`](flujo-operativo.html) | **Flujo operativo por etapas:** Onboarding → Auditoría acotada → Reparación en workspace → QA independiente → Cierre. |
| `sequence` | `secuencia-ejecucion.sequence.json` | [`secuencia-ejecucion.html`](secuencia-ejecucion.html) | **Secuencia de llamadas y herramientas:** intercambio entre Operador, DSH Agent, missions.py runner/verify, Workspace y QA subagent. |
| `lifecycle` | `ciclo-vida-unidad.lifecycle.json` | [`ciclo-vida-unidad.html`](ciclo-vida-unidad.html) | **Máquina de estados de la unidad:** transiciones entre PLANNED, AUTHORIZED, CANDIDATE, VERIFIED, ACCEPTED, RETAINED y UNVERIFIED. |
| `dataflow` | `flujo-datos-evidencia.dataflow.json` | [`flujo-datos-evidencia.html`](flujo-datos-evidencia.html) | **Cadena criptográfica de evidencia:** flujo de hashes SHA-256 desde task.json hasta check-base/ (rojo), check-1/ (verde), qa.json y result.json. |

## Validación y entrega

Para volver a validar o compilar los diagramas:

```bash
cd /home/alan/.agents/skills/archify

# Validación showcase (9/9 checks + 0 issues de composición):
node bin/archify.mjs validate architecture /home/alan/Documents/Improvement/docs/diagrams/flujo-arquitectura.architecture.json --quality showcase --json
node bin/archify.mjs validate workflow /home/alan/Documents/Improvement/docs/diagrams/flujo-operativo.workflow.json --quality showcase --json
node bin/archify.mjs validate sequence /home/alan/Documents/Improvement/docs/diagrams/secuencia-ejecucion.sequence.json --quality showcase --json
node bin/archify.mjs validate lifecycle /home/alan/Documents/Improvement/docs/diagrams/ciclo-vida-unidad.lifecycle.json --quality showcase --json
node bin/archify.mjs validate dataflow /home/alan/Documents/Improvement/docs/diagrams/flujo-datos-evidencia.dataflow.json --quality showcase --json

# Entrega de artefactos HTML:
node bin/archify.mjs deliver architecture /home/alan/Documents/Improvement/docs/diagrams/flujo-arquitectura.architecture.json /home/alan/Documents/Improvement/docs/diagrams/flujo-arquitectura.html --quality showcase --json
node bin/archify.mjs deliver workflow /home/alan/Documents/Improvement/docs/diagrams/flujo-operativo.workflow.json /home/alan/Documents/Improvement/docs/diagrams/flujo-operativo.html --quality showcase --json
node bin/archify.mjs deliver sequence /home/alan/Documents/Improvement/docs/diagrams/secuencia-ejecucion.sequence.json /home/alan/Documents/Improvement/docs/diagrams/secuencia-ejecucion.html --quality showcase --json
node bin/archify.mjs deliver lifecycle /home/alan/Documents/Improvement/docs/diagrams/ciclo-vida-unidad.lifecycle.json /home/alan/Documents/Improvement/docs/diagrams/ciclo-vida-unidad.html --quality showcase --json
node bin/archify.mjs deliver dataflow /home/alan/Documents/Improvement/docs/diagrams/flujo-datos-evidencia.dataflow.json /home/alan/Documents/Improvement/docs/diagrams/flujo-datos-evidencia.html --quality showcase --json

# Verificación visual en navegador headless real (1440x900 a 2048x1320):
for f in /home/alan/Documents/Improvement/docs/diagrams/*.html; do
  node bin/archify.mjs visual-check "$f" --json
done
```
