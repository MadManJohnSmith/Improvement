# Estado de la distribución

## Entregado y comprobado localmente

- Arquitectura normativa completa, separada de historial y hechos privados.
- Inicializador Python sin dependencias: dry-run, creación explícita, perfil mínimo y repetición sin sobrescribir; rechazo de rutas internas, traversal, enlaces, identidades inválidas y conflictos.
- `python3 -B -m unittest discover -s tests -v`: **4 tests aprobados** con múltiples aserciones en directorio temporal; producto sintético conservado, permisos de workspace comprobados. No es una prueba de sandbox, carreras hostiles ni recuperación tras corte eléctrico.
- Cinco skills con frontmatter: cuatro procedimientos portables conservados y una incorporación nueva. Carga determinista de las cinco mediante registro y `ctx.tools.execute` nativos del runtime instalado 0.1.5-rc.1, en alcance de agente: padre=0, workspace=5, cuerpo y origen verificados. Regresión `tests/test_dsh_skill_root.mjs`, sin modelos. Además, trayectoria real de Standard revisada: carga nativa de `workflow-bounded-acceptance` desde el workspace externo y tres turnos sobre un caso sintético: aceptación con mejora opcional, retención por cita inventada y cierre tras corrección. Un cuarto turno ante resultados de tests requeridos pero ausentes devolvió UNVERIFIED, sin confundir ausencia con tests fallidos y solicitando evidencia ligada al candidato. Sin llamadas de escritura en esos turnos. Valida estos casos guiados, no todas las skills ni autonomía; fuentes estipuladas, sin verificación externa de citas. Historial privado conservado fuera del repositorio.
- Archivo original movido íntegramente a directorio hermano privado, con mapeo externo. Repositorios anidados y candidatos conservados; ningún archivo histórico forma parte del staging publicable.

## Antecedentes externos, no pruebas de esta distribución

El kit previo contiene publicador/resolver Cordis y ensayos deterministas reportados, fixture de contrato y QA del piloto. Su lector está ligado a tres archivos de un caso, sus bindings y scripts tienen alcance de ensayo; no se distribuye como adaptador universal. Se preservó todo el código en el archivo externo para reutilización dirigida, no se reconstruyó ni se ejecutó. El enlace histórico de dependencias al producto permanece intacto; el archivo no es operativo.

El paquete instalado DSH 0.1.5-rc.1 fue inspeccionado y sus servicios nativos ejecutados con Node 26.8.1. Ver setup-dsh.md para alcance y reproducción.

## Pendiente

Evaluación de las otras skills y aceptación sobre candidatos con evidencia ejecutable real, evaluación de tres escenarios de incorporación, adaptación portable del publicador, presets de los dos modos, continuación Host, QA/reauditoría automática, límites durables, recuperación y transferencia a segundo proyecto real. No hubo llamadas de modelos, instalación, cambios globales ni QA independiente en esta reorganización.

Remoto origin configurado; publicación sujeta a autorización y autenticación efectiva. El repositorio es canónico: artefactos de ejecución y datos privados permanecen fuera del árbol. `AGENTS.md` establece las reglas de mantenimiento y evaluación con DSH Standard. Licencia pública pendiente del titular. La preparación para GitHub no equivale a publicación ni a motor completo.
