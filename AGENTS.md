# Reglas del repositorio canónico

Este repositorio contiene el flujo distribuible, no el workspace de un proyecto usuario. Consultar ARQUITECTURA_FLUJO_AGENTES.md como diseño vigente y docs/status.md como estado comprobado. Actualizar el mismo documento de arquitectura cuando cambie el diseño; el historial va en Git y CHANGELOG.md, no como diario dentro de la arquitectura.

## Contenido y límites

- Versionar únicamente código, skills, documentación y pruebas de regresión permanentes del propio flujo. `tests/` contiene código mantenido del framework, nunca resultados ni datos reales de una ejecución.
- Alojar proyectos desechables, perfiles de proyectos reales, informes de sesiones, logs, capturas, candidatos, salidas y cachés fuera del repositorio, en un directorio hermano de pruebas o temporal explícito. No basta con ignorarlos en Git.
- No instalar dependencias, copiar runtimes, crear worktrees de prueba ni generar bytecode dentro de este árbol para un ensayo. Usar destinos externos; Python con `-B` cuando corresponda. Las misiones operativas no pueden editar este árbol canónico para adaptar sus propias instrucciones; las propuestas se devuelven o se aplican en una misión de mantenimiento separada.
- No incluir credenciales, datos personales, auditorías privadas ni rutas locales del mantenedor en archivos publicables. No seguir enlaces para modificar recursos ajenos.
- No publicar ni hacer push sin autorización del destino. Los commits locales del flujo están autorizados; revisar el diff y los archivos preparados antes de cada commit. Las reglas de revisión viven en `CODING_STANDARDS.md`; el revisor las aplica, el implementador no las necesita.

## Desarrollo y evaluación

El mantenedor guía ensayos con DSH Standard, evalúa evidencia real de las sesiones y convierte fallos relevantes en cambios del flujo y regresiones. Standard y los modos/skills genéricos del MVP son herramientas de construcción y fixtures; **no son la distribución final para proyectos nuevos**. Tras C0–C7, Creator generará `<Proyecto>-auditor` y `<Proyecto>-continuous-repair` específicos. Los IDs de sesión de DSH no son IDs de ZCode: usar una fuente disponible y autorizada, sin inventar acceso entre sistemas ni importar historiales privados al repo.

Preservar evidencia externa de fallos, deduplicar causas y hacer cambios mínimos. No repetir toda la arquitectura ni exigir aprobación por cada subpaso ya autorizado. No afirmar autonomía, carga de skills o aislamiento a partir de un prompt o un estado declarativo.

Antes de cerrar una unidad: ejecutar las comprobaciones pertinentes con salidas externas, actualizar estado/documentación si corresponde, revisar lo que se versionará y dejar el árbol limpio tras un commit autorizado. Si hay trabajo ajeno, no descartarlo ni incluirlo para aparentar limpieza; señalarlo.

No cerrar el turno con un plan o una promesa: ejecutar el siguiente paso. Devolver el control solo ante un bloqueo real o una decisión que solo el usuario pueda tomar.

## Agent skills

Las tres secciones siguientes son la configuración por repositorio que asumen las skills de ingeniería. La mantiene el mantenedor con `/setup-matt-pocock-skills` (invocación manual, no un paso que el agente decida por su cuenta); para elegir qué skill o flujo aplica a un encargo, el mantenedor usa `/ask-matt`, que enruta sobre las skills instaladas. No mantengas aquí un catálogo de skills en paralelo al router.

### Issue tracker

Issues and specs are tracked in GitHub Issues (`MadManJohnSmith/Improvement`) using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles mapped 1:1 to default label names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`GLOSSARY.md` at the repository root and ADRs in `docs/adr/`). See `docs/agents/domain.md`.
