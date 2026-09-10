# Reglas del repositorio canónico

Este repositorio contiene el flujo distribuible, no el workspace de un proyecto usuario. Consultar ARQUITECTURA_FLUJO_AGENTES.md como diseño vigente y docs/status.md como estado comprobado. Actualizar el mismo documento de arquitectura cuando cambie el diseño; el historial va en Git y CHANGELOG.md, no como diario dentro de la arquitectura.

## Contenido y límites

- Versionar únicamente código, skills, documentación y pruebas de regresión permanentes del propio flujo. `tests/` contiene código mantenido del framework, nunca resultados ni datos reales de una ejecución.
- Alojar proyectos desechables, perfiles de proyectos reales, informes de sesiones, logs, capturas, candidatos, salidas y cachés fuera del repositorio, en un directorio hermano de pruebas o temporal explícito. No basta con ignorarlos en Git.
- No instalar dependencias, copiar runtimes, crear worktrees de prueba ni generar bytecode dentro de este árbol para un ensayo. Usar destinos externos; Python con `-B` cuando corresponda. Las misiones operativas no pueden editar este árbol canónico para adaptar sus propias instrucciones; las propuestas se devuelven o se aplican en una misión de mantenimiento separada.
- No incluir credenciales, datos personales, auditorías privadas ni rutas locales del mantenedor en archivos publicables. No seguir enlaces para modificar recursos ajenos.
- No publicar ni hacer push sin autorización del destino. Revisar el diff y los archivos preparados antes de cada commit.

## Desarrollo y evaluación

El mantenedor guía ensayos con DSH Standard, evalúa evidencia real de las sesiones y convierte fallos relevantes en cambios del flujo y regresiones. Standard es el entorno de construcción; los modos finales siguen siendo Auditor y Reparación continua. Los IDs de sesión de DSH no son IDs de ZCode: usar una fuente disponible y autorizada, sin inventar acceso entre sistemas ni importar historiales privados al repo.

Preservar evidencia externa de fallos, deduplicar causas y hacer cambios mínimos. No repetir toda la arquitectura ni exigir aprobación por cada subpaso ya autorizado. No afirmar autonomía, carga de skills o aislamiento a partir de un prompt o un estado declarativo.

Antes de cerrar una unidad: ejecutar las comprobaciones pertinentes con salidas externas, actualizar estado/documentación si corresponde, revisar lo que se versionará y dejar el árbol limpio tras un commit autorizado. Si hay trabajo ajeno, no descartarlo ni incluirlo para aparentar limpieza; señalarlo. La autorización del usuario cubre commits locales del flujo; no cambios de producto ni publicación remota.
