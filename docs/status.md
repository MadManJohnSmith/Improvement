# Estado de la distribución

## Entregado y comprobado localmente

- Arquitectura normativa completa, separada de historial y hechos privados.
- Inicializador Python sin dependencias: dry-run, creación explícita, perfil mínimo y repetición sin sobrescribir; rechazo de rutas internas, traversal, enlaces, identidades inválidas y conflictos.
- `python3 -B -m unittest discover -s tests -v`: **1 test aprobado** con múltiples aserciones en directorio temporal; producto sintético conservado, permisos de workspace comprobados. No es una prueba de sandbox, carreras hostiles ni recuperación tras corte eléctrico.
- Cinco skills con frontmatter: cuatro procedimientos portables conservados y una incorporación nueva. Inspección estática, no evaluación de comportamiento LLM ni carga DSH.
- Archivo original movido íntegramente a directorio hermano privado, con mapeo externo. Repositorios anidados y candidatos conservados; ningún archivo histórico forma parte del staging publicable.

## Antecedentes externos, no pruebas de esta distribución

El kit previo contiene publicador/resolver Cordis y ensayos deterministas reportados, fixture de contrato y QA del piloto. Su lector está ligado a tres archivos de un caso, sus bindings y scripts tienen alcance de ensayo; no se distribuye como adaptador universal. Se preservó todo el código en el archivo externo para reutilización dirigida, no se reconstruyó ni se ejecutó. El enlace histórico de dependencias al producto permanece intacto; el archivo no es operativo.

Fuente del loader inspeccionada en el checkout suministrado, revisión `5dda764ed3aa172535a7967b06ff95d9cbfe536a`; no equivale a inspección del paquete DSH 0.1.5-rc.1 reportado. Ver setup-dsh.md.

## Pendiente

Carga real de skills en el runtime efectivo, evaluación de tres escenarios de incorporación, adaptación portable del publicador, presets de los dos modos, continuación Host, QA/reauditoría automática, límites durables, recuperación y transferencia a segundo proyecto real. No hubo llamadas de modelos, instalación, cambios globales ni QA independiente en esta reorganización.

Git local en `main`, sin remoto; identidad de autor configurada por autorización del titular. El repositorio es canónico: artefactos de ejecución y datos privados permanecen fuera del árbol. `AGENTS.md` establece las reglas de mantenimiento y evaluación con DSH Standard. Licencia pública pendiente del titular. La preparación para GitHub no equivale a publicación ni a motor completo.
