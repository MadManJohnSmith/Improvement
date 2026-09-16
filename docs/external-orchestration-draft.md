# Borrador: expansión de orquestación externa — specs EARS, kanban de worktrees e índice local

**Estado:** BORRADOR de propuesta. Nada de este documento es decisión aceptada, implementación ni evidencia.
**Fecha:** 2026-09-13
**Subordinado a:** [ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) (diseño normativo vigente, v2.4)
**Origen:** análisis del mantenedor con ZCode sobre capacidades de herramientas agénticas de terceros (Factory/droid, Cursor, AWS Kiro, Vibe Kanban, Aider) y su encaje con el flujo existente.

Este borrador no compite con la arquitectura normativa ni con [PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md): propone qué capacidades de terceros valen la pena evaluar, cuáles se rechazan y cómo se mapearían sobre las piezas ya implementadas. Cualquier adopción pasa primero por las reglas habituales: decisión del mantenedor, actualización de la arquitectura y acreditación por separado.

## 1. Hechos de entorno sobre los que se apoya la propuesta

Verificados el 2026-09-13; re-verificar en el momento de implementar.

- **9router** opera como capa de inferencia del Host con combos `Orquestrador`, `Subagents`, `ATM`, `Subagents-Audits`, `Subagents-Coding` (cadenas de fallback sobre múltiples proveedores y cuentas, round-robin). Existen dos canales por cliente: NORMAL y RAW (`x-9router-token-saver: off`), que conmutan compresión RTK/Ponytail por petición. El mapeo autorizado de roles (§15 de la arquitectura: orquestador y QA por canal RAW, ejecución por canal NORMAL) ya está aplicado en el Host.
- **Clientes alternativos de ejecución**: Codex CLI (v0.153.4) tiene perfiles por combo (`orquestrador`, `audits`, `coding` y variantes `-raw`) con `wire_api="responses"` soportado por 9router. Permite ejecutar unidades headless (`codex exec --profile …`) sin pasar por DSH.
- **Piezas del framework reutilizables**: `scripts/host_launcher.py` (aislamiento fail-closed bubblewrap), `scripts/inference_channel.py` (inferencia acotada por lanzamiento), `scripts/publisher.py` (recibos), `scripts/budget.py` (ledger de límites), `scripts/missions.py` (`verify`/`reaudit` mecánicos), `scripts/audit.py` (partición/inventario), presets DSH con `subagent-model-selection` apuntando a 9router.
- **Herramientas externas evaluadas** (investigación web, pendiente de verificación práctica): Vibe Kanban (BloopAI, open source, Rust) orquesta agentes CLI (Claude Code, Codex, Gemini CLI, Amp) con un worktree de git por tarjeta; AWS Kiro formaliza requirements en formato EARS con tareas y criterios de aceptación; Factory/droid ofrece Missions (milestones con git handoffs), Spec Mode y revisión de PRs por evento (Droid Review); Cursor ofrece Tab predictivo, memories e indexado semántico — todos en nube ajena.

## 2. Evaluación de encaje por funcionalidad

Criterio de encaje: respeta unidades de autorización, evidencia mecánica, un escritor por entorno, privacidad de datos y ausencia de dependencia de nubes ajenas para código/estado.

| Funcionalidad (origen) | Encaje | Lectura |
|---|---|---|
| Missions: milestones + git handoffs (Factory) | **Patrón, no producto** | Coincide con la etapa 4 (handoff determinista) y el ciclo por `cycle_id`. No adoptar el producto; el patrón ya está en la arquitectura y parcialmente en `missions.py`. |
| Spec Mode / specs durables (Factory, Kiro, spec-kit) | **Alto** — propuesta F1 | El framework ya exige criterios de aceptación por mandato (§6) pero no una spec como artefacto versionado consumible por workers. EARS aporta verificabilidad mecánica. |
| Droid Review / Bugbot: revisión de PRs por evento (Factory, Cursor) | **Medio** — propuesta F3, condicionada | El disparo por evento y el delta por push no existen en el flujo. La publicación de hallazgos externos debe pasar por el contrato del publicador (§8), no por una integración ad-hoc. |
| Tab predictivo, fast-apply, modelos propietarios (Cursor) | **Rechazado** | Dependencia de modelos cerrados y nube ajena; no replicable; contradice no objetivos. |
| Indexado semántico del codebase en nube (Cursor, Factory) | **Rechazado como servicio; sustituto local en F5** | El codebase completo nunca debe residir en nubes ajenas. El sustituto local es una pieza nueva que hay que diseñar con presupuesto de crecimiento (ver F5). |
| Memories en nube (Cursor) | **Rechazado como servicio; sustituto local en F5 (capa C)** | Ídem. La memoria de decisiones ya tiene contrato en §7; la episódica es complementaria y debe decaer. |
| Vibe Kanban: 1 tarjeta = 1 worktree = 1 agente CLI | **Alto como ensayo** — propuesta F4 | Da la superficie de ejecución paralela con aislamiento por worktree sin desarrollarla. No es un "dashboard vacío": ejecuta unidades reales. Riesgo: su flujo de git/merge debe someterse a los controles del Host, no sustituirlos. |
| Repo map por tree-sitter (Aider) | **Alto** — parte de F5 | Contexto estructurado barato para el orquestador; encaja con "rutas y símbolos son localizadores, no prueba de equivalencia semántica" (§7). |
| container-use / sandbox por contenedor (Dagger) | **Bajo por ahora** | `host_launcher.py` ya es el rig de aislamiento local. Un contenedor por agente solo si el launcher resulta insuficiente para paralelismo real. |
| Agentes en nube que producen PRs (Jules, Devin, Copilot coding agent) | **Rechazado** | Código y estado fuera del entorno; contra privacidad y contra el modelo de autorización local. |

## 3. Diseño propuesto por fases (borrador)

Cada fase declara: objetivo, qué se reutiliza, qué es nuevo y su criterio de salida. Ninguna fase está autorizada ni implementada.

### F1 — Specs EARS como artefacto del mandato

- **Objetivo:** que toda misión no trivial produzca `requirements.md` (sentencias EARS verificables), `design.md` opcional y `tasks.md` (tareas con criterios de aceptación por tarea y dependencias), como archivos del estado de la misión.
- **Reutiliza:** mandato de misión (§6), aceptación sin bucles (§9), workspace externo (§14).
- **Nuevo:** plantilla/skill de especificación; convención de dónde viven los archivos (decisión abierta D1).
- **Criterio de salida:** una misión de ensayo donde Executor/QA/Auditor consumen las tareas por referencia a `tasks.md` y `missions.verify` valida contra los criterios declarados, no contra texto de conversación.

### F2 — Loop de validación Coding→Audits acotado

- **Objetivo:** tras cada tarea implementada, un auditor independiente evalúa contra el criterio EARS de esa tarea; defecto → corrección (máximo acotado, ya existe el límite de dos intentos en v0.1); aceptación → siguiente unidad.
- **Reutiliza:** roles executor/QA/auditor con `actor_id` distinto (etapa 4), `missions.verify`/`reaudit`, `budget.py` para el presupuesto del loop.
- **Nuevo:** nada estructural; es composición de mecanismos existentes sobre las specs de F1.
- **Criterio de salida:** ciclo sintético donde la aceptación de una tarea exige veredicto del auditor con evidencia, y el presupuesto corta el loop de forma determinista.

### F3 — Revisión por eventos (diff → auditoría → publicación externa)

- **Objetivo:** que un commit/PR dispare una unidad de auditoría incremental sobre el delta y publique hallazgos como comentarios externos, sin intervención humana por evento.
- **Reutiliza:** `reaudit` incremental (§13), `host_launcher.py` para la ejecución aislada, executor headless (Codex perfiles o DSH).
- **Nuevo:** disparador (hook local o CI), y una decisión de contrato: cómo se publica fuera sin romper las propiedades del publicador (§8: identidad real, autorización, idempotencia). No usar `gh` ad-hoc como publicador paralelo sin resolver esto.
- **Criterio de salida:** ensayo donde un push genera auditoría del delta con hallazgos publicados y re-verificables, y un segundo push no repite la auditoría completa.

### F4 — Kanban de worktrees como ensayo de ejecución paralela

- **Objetivo:** evaluar Vibe Kanban como superficie de coordinación visual de unidades paralelas, cada una en su worktree, ejecutadas por perfiles Codex hacia 9router (o por DSH si se integra).
- **Reutiliza:** canal dual 9router (NORMAL/RAW) por rol; perfiles Codex existentes; límite de un escritor por entorno (§11) — el worktree es el entorno.
- **Riesgos a probar antes de adoptar:** el flujo de git/merge de la herramienta no debe eludir el publicador ni la autorización de integración; los candidatos y recibos deben seguir viviendo en el estado externo del framework; evaluar qué datos del repo expone la herramienta.
- **Criterio de salida:** un ensayo con dos unidades paralelas independientes ejecutadas, evidencia conservada en el formato del framework y merge solo tras aceptación.

### F5 — Índice local del codebase y memoria episódica (sustituto local del indexado en nube)

Pieza nueva más importante; diseñar antes de construir. Tres capas con ciclos de vida distintos:

- **Capa A — artefactos del trabajo** (specs, decisiones, convenciones): viven en git, no necesitan base de datos; su crecimiento lo acota el ciclo de vida del feature. Ya cubierto por F1 y §7; no reinventar.
- **Capa B — índice del codebase**: chunking por símbolos con tree-sitter (funciones/clases/docstrings, no ventanas de texto), embeddings 100% locales (modelo pequeño de embedding en CPU; p. ej. vía Ollama o fastembed), almacenamiento en SQLite+sqlite-vec (un archivo por repo, fuera del árbol canónico), re-indexado incremental por hash de contenido. Acceso **pull-based** vía MCP o CLI: el agente consulta cuando su tarea lo requiere y recibe solo los chunks relevantes.
- **Capa C — memoria episódica**: aprendizajes entre sesiones con compaction jerárquica (entrada → resumen por módulo → caducidad LRU con TTL), presupuesto duro por repo y archivo en git de lo que sale de caliente.
- **Invariantes exigidos:** todo local (ningún embedding ni código en nubes ajenas); crecimiento acotado (presupuestos por repo, decaimiento, consolidación); jerarquía progresiva (repo map siempre cargado y pequeño → resúmenes → chunks a demanda) para no inflar tokens; el índice es un **localizador**, no prueba de nada (misma regla que §7 para rutas y símbolos).
- **Relación con la memoria de decisiones de §7:** complementaria. La de §7 es el contrato normativo de decisiones técnicas; las capas B/C son herramientas de acceso y recuerdo, sin autoridad.
- **Criterio de salida:** un ensayo donde un executor encuentra los símbolos pertinentes de un repo mediano vía consulta al índice, con medición de tokens consumidos frente a navegación manual, y con el índice demostrando re-indexado incremental y presupuesto respetado.

## 4. Decisiones abiertas (requieren decisión del mantenedor)

- **D1 — Ubicación de las specs:** dentro del workspace externo de la misión (estado de la misión) vs. dentro del árbol del producto (cuando el producto las debe versionar). Afecta a §14.
- **D2 — Ejecutor de las tarjetas kanban:** perfiles Codex existentes (menor integración, ya opera sobre 9router) vs. plugin/integración DSH (más control, más trabajo). Vibe Kanban no soporta DSH como agente nativo hoy.
- **D3 — Contrato de publicación de hallazgos externos (F3):** nuevo binding del publicador vs. retención local con notificación. Requiere decisión antes de implementar F3.
- **D4 — Motor de embeddings y presupuesto de la capa B:** modelo, dimensiones, presupuesto de vectores por repo y política TTL/LRU concreta.
- **D5 — Si F4 se adopta, qué datos del repo se exponen a la herramienta** y quién posee el worktree (Host vs. herramienta).

## 5. No objetivos (coherentes con §2 de la arquitectura)

- No adoptar plataformas de agentes en nube ni suscripciones cuyo modelo de valor sea infraestructura ajena (Jules, Devin, Factory Pro como plataforma).
- No perseguir Tab predictivo ni fast-apply propietarios.
- No construir una plataforma universal nueva ni un dashboard sin trabajo real detrás.
- No introducir dependencias de nube para embeddings, índices ni memorias.

## 6. Procedencia

Análisis de capacidades de terceros basado en documentación pública verificada el 2026-09-13 (Factory docs, repositorios y comparativas citadas en la sesión de origen). Los hechos de entorno (combos y canales de 9router, perfiles Codex, piezas de `scripts/`) corresponden al estado comprobable del Host en esa fecha; su vigencia se re-verifica al implementar. Este borrador no acredita ejecución: las etapas de [PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md) siguen siendo la única matriz de estado.
