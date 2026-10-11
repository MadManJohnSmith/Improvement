# Lecciones de las campañas de workflows (ZCode) y del flujo agéntico

**Vista de una página.** Cada fila es un fallo o un éxito **medido**, atribuido a la
evidencia que lo produjo. No es un resumen de las campañas: es lo que hay que
repetir y lo que hay que impedir, con la prueba permanente que lo sostiene.

**Qué evidencia hay y qué no.** Este documento se escribió **sin acceso al journal
de los runs**. `ListWorkflowRuns` y `GetWorkflowRun` no están disponibles en la
sesión que lo redactó: la respuesta fue `workflow_introspection_unavailable`, una
carencia de capacidad, no un proyecto vacío. Lo único que persiste en
`.zcode/workflow-runs/` y `~/.zcode/workflow-runs/` es el **programa lowered**
(`dwfrun-*.mjs`), no el journal ni los artefactos: no hay veredicto por run, no
hay `log()`, no hay token usage. Por tanto:

- «Run terminó» **no** es «hallazgo correcto». Un run puede cerrar `COMPLETED`
  con el hallazgo equivocado dentro.
- «Gate verde local» **no** es «DSH real». Las pruebas del árbol usan cliente
  falso inyectado; solo algunas campañas ejecutaron sesión DSH real.
- Lo que aquí se afirma como *contraejemplo con éxito contrario* sale de un
  `run.json`, de una observación o de un test que se puede volver a ejecutar.
  Lo demás queda marcado `SIN PRUEBA`.

**Regla de atribución.** Cada fila nombra un run id (`dwfrun-…`/`dwfeval-…`), un
sha, un `r-…` de run del ejecutor o una ruta+linea. Sin uno de esos, la fila es
folklore y no entra.

---

## 1. Matriz atribuible de lecciones

`L<nn>` es el identificador. La columna *Prueba* apunta a la regresión
permanente; `—` significa que la barrera es de documentación o de otra prueba ya
existente, y se dice cuál.

### 1.1 Fallos y cómo quedaron cerrados

| ID | Síntoma | Causa verificada | Barrera preventiva | Prueba | Éxito contrario |
|---|---|---|---|---|---|
| L01 | Un gate de campaña daba verde sin haber leído la suite | `unittest` escribe recuento y veredicto en **stderr**; el gate parseaba solo stdout y no veía `Ran N tests` | El parser de veredicto une los dos flujos antes de extraer nada | `tests/test_workflow_lessons.py` ([W01]) | `dwfrun-27cccb98` documentó el defecto en su propio comentario de código |
| L02 | `MEMORY_RECONCILED {invalidated: 6, hits: 0}` publicado igualmente | La memoria mide sobre la instantánea del workspace, no sobre la base del producto | La reconciliación invalida el grupo entero ante contexto distinto y lo registra en journal | `tests/test_workflow_lessons.py` ([W02]) | `docs/status.md:175` publica el registro con las 6 invalidaciones declaradas, no escondidas |
| L03 | Índice de memoria que sobrevive a un gate que falló | Publicar memoria tras `RUN_COMPLETED` solo, sin mirar el veredicto del gate | Memoria solo tras run terminal; un run `RETAINED` no publica | `tests/test_workflow_lessons.py` ([W03]) | `r-5d7d11…` quedó `RETAINED cause: gate-abort:gate-producto` y no publicó |
| L04 | Reanudar reejecutaba todo y perdía el run | `_run_id_for` se calculaba por contenido mutable en vez del sha del plan | El id del run sale del sha del plan: el mismo plan reanuda el mismo run dir | `tests/test_workflow_lessons.py` ([W04]) | `r-7761c0…` reanudó y llegó a `COMPLETED` con 11→14 eventos |
| L05 | Un `MEMORY_RECONCILED` con run terminado pero sin PASS/FAIL coherente | La publicación de memoria se intentaba fuera del cierre terminal y podía reescribir el veredicto | El fallo de publicación se registra sin convertir el veredicto en PASS o FAIL a posteriori | `scripts/workflow.py:1796-1803` + `tests/test_workflow_memory.py` | Run con `memory_error` registrado y veredicto intacto |
| L06 | Portadas afirmaban `848 pruebas en verde` con 932 en el árbol | La suite creció sin commitear; la cifra publicada describía `HEAD` | El test de consistencia **descubre** la cifra y exige que una antigua se declare antigua | `tests/test_architecture_consistency.py:352` | `README.md:290`/`README.es.md:289` publican 933, descubiertas, no recordadas |
| L07 | La suite ensuciaba su propia salida con `usage:` en stderr | CLIs que deben salir con 2 escriben en stderr, y los tests solo redirigen stdout | La salida de los subprocesos se captura completa en cada regresión | `tests/test_architecture_consistency.py:386` | Suite corre sin `usage:` sobre la línea de puntos |
| L08 | Cifras «verdes» repetidas en dos documentos | Dos recuentos escritos a mano a dieciséis líneas de distancia | Una sola cifra por documento, descubierta, más una prueba que la coteja | `tests/test_architecture_consistency.py:352` | Un único sitio publica la cuenta, y el test la verifica |
| L09 | Creator real no persistió `generated/generation-manifest.json` | El turno headless de 29 tool calls quedó quiescente sin artefacto; tras medirlo, la causa fue la sesión sin el overlay `--patch`, que hacía caer `write` en la fila de upstream rechazada por el sandbox | Un paquete aceptado tiene que nombrar quién lo produjo; el argv headless pasa por la función oficial que compone el overlay | `docs/status.md:205-212` (§Pase integral), ensayo externo `ensayo-x3-actualizado.md:18-28` | El paquete del pase lo produjeron herramientas deterministas, **no** el modelo; después, X3 con overlay sí generó 19 artefactos y fue ACTIVE, **antes** del arreglo del presupuesto |
| L10 | Corpus gate sin endpoint evaluator ni adaptador Host | El diagnóstico de arranque era **falso**: `dsh web` sí arrancaba; el home copiado tenía `profiles/web/node_modules/` vacío. Lo que **no existe** en `0.2.0-rc.2` es un endpoint `evaluator`, y lo que no ofrece el CLI es el adaptador que verifica layout/skill efectiva antes de `session/create` | El gate se abstiene fail-closed nombrando la pieza que falta y no inventa endpoint ni veredicto | `docs/status.md:187-215` (§Pase integral), `scripts/skill_gate_run.py:604-608`, `tests/test_skill_gate_run.py` | `action: reject` en la partición antifraude: el candidato inventado perdió 0.488 < 1.000 |
| L11 | Candidata de reparación sin worktree del producto | `git worktree add` bloqueado por el sandbox: `Read-only file system` + `[sandbox: file access denied]` | La candidata nace como repositorio sombra que provisiona el Host bajo el workspace (contrato `Host-provision_repair-shadow-only`) | `docs/status.md:210-226` (§Pase integral), `tests/test_mode_lifecycle.py` | `x1-live/RESULTADO.md`: DSH headless real persistió `PROVISIONED → DIRTY`, diff verificado, tests 3/3; el preset real sólo se cargó en `x1-preset-real`, que se detuvo antes de editar |
| L12 | Attempt de escalada de permisos | El modo intentó `danger-full-access` sin canal de aprobación | Anti-escalación exacta: prohibidos `sandbox_permissions`/`justification` con cualquier valor; denegación o error de schema → `RETAINED` sin reintento | `ARQUITECTURA_FLUJO_AGENTES.md:160` + `tests/test_mode_lifecycle.py` | `docs/status.md:180`: reintento con `danger-full-access` rechazado sin canal |
| L13 | Evaluador de corpus recibía la respuesta esperada | El prompt del evaluador llevaba marcado el veredicto esperado | El prompt de evaluación nunca contiene la respuesta esperada | `tests/test_skill_gate_run.py:114` | Un candidato sin evidencia no queda cubierto: se reporta como ocurrió |
| L14 | Un fichero de informe servía de ruta y la publicación fallaba | El corrector devolvía prosa con la ruta dentro, y esa prosa se usó como ruta | La ruta canónica se conoce fuera de la respuesta del subagente | `dwfrun-d8fb7dd5` (comentario del propio script, corregido en su reenvío) | El informe quedó publicado como artefacto en el reenvío |
| L15 | Un subagente leyó rutas locales del mantenedor dentro del informe | El encargo incluía rutas personales esperando que el arqueólogo las usara | Los encargos a subagentes prohíben rutas locales y material de terceros | `tests/test_architecture_consistency.py:175-188` | `dwfrun-577fa719` trabajó con `git show <sha>:<ruta>`, sin rutas vivas |
| L16 | Preset verificado pero skill no descubierta | `description` sin comillas con `: ` dentro rompía el frontmatter (`Nested mappings are not allowed in compact mappings`) | `host_validator.skill_frontmatter_issue` rechaza el frontmatter no parseable antes de publicar | Ensayo externo `corpus-fixed/RESULTADO.md:5-9` (negativo con DSH real) | Tras entrecomillar el frontmatter, `skills/list` devolvió 4 skills `modelInvocable` y la llamada `skill` devolvió contenido |
| L17 | Caso de corpus compilaba una **skill** y despachaba a un **modo** | `SC-123` apuntaba a `source-driven-development`, pero el gate despachó al modo `fixture-auditor`; el modo exigió el layout `<producto>/<workspace>` que el directorio del caso no tenía y narró `RETAINED` sin `workflow_write` | Targeting y layout explícitos antes de aceptar un caso como prueba de modo; el gate sigue leyendo `result.json`, nunca prosa | Ensayo externo `corpus-fixed/RESULTADO.md:11-23` | `NOT_COVERED` con evidencia, no PASS inventado |

### 1.2 Casos de éxito que hay que conservar

| ID | Qué salió bien | Evidencia | Prueba |
|---|---|---|---|
| L18 | `FAIL → repair → PASS` completo en ejecutor con memoria | `r-5d7d11…` retenido por gate; `r-7761c0…` completado reparado | `tests/test_workflow_memory.py:360` |
| L19 | Memoria incremental entre campañas con producto git sintético | 22 pruebas: cambio/borrado/rename/base/config, symlink, memoria malformada, dos planes | `tests/test_workflow_memory.py:66-477` |
| L20 | Preflight headless real contra DSH 0.2.0-rc.2 | `PING-OK`, `turn_end.reason.kind = completed`, `totalTokens = 6509` | `docs/status.md:174` (entorno, no prueba automatizada) |
| L21 | Skills cargadas e invocadas en sesión DSH real | auditor 3, reparador 2, implementador 1; turno trivial → 0 tool calls | `docs/status.md:176` |
| L22 | Abstención real verificada con write-probe | `Decision: I abstain`; producto intacto tras el intento | `docs/status.md:177` |
| L23 | Validador Host sobre paquete real | `READY_FOR_ACCEPTANCE`, 10/10 capas PASS | `docs/status.md:178` |
| L24 | Corpus gate antifraude contra candidato inventado | `action: reject`, 0.488 < 1.000 en partición de entrenamiento | `docs/status.md:179` + `tests/test_corpus_gate.py` |
| L25 | Confinamiento canónico denegando escritura desde el repo | Intento denegado; reintento escalado rechazado | `docs/status.md:180` |
| L26 | Implementador real con candidata externa aceptada | commit `95aa9b2`, 6/6 tests nuevos, producto intacto, sin commit/merge/push implícitos | `docs/status.md:9` |
| L27 | Fuentes externas tratadas como no confiables y reproducidas | Cada afirmación que sostenía un cambio de código se verificó en el árbol antes de cambiar código | `fuentes-memoria.md` (evidencia externa) y `dwfrun-0666568b`, cuyo programa inferior repite la orden: el pase arranca por inventario, no por el informe previo |
| L28 | Reconciliación idéntica sin reescritura | Índice distinto no se pisa; bytes idénticos reproducen el mismo índice | `tests/test_workflow_lessons.py` ([W06]); `git show HEAD:scripts/workflow_evidence.py:276-309` |
| L29 | Reenvío de campaña que arrastra el arreglo del intento anterior | `dwfrun-d8fb7dd5` corrigió la lección de `finalPath` en su reenvío | `dwfrun-d8fb7dd5` |

---

## 2. No probado: lo que estos runs no demuestran

Ninguna de estas filas se rellena con suposición; todas quedan declaradas.
La **cobertura** real de las campañas es esta tabla, no el recuento de lecciones.

| Hueco | Por qué no está probado | Dónde se declara |
|---|---|---|
| No hay acceso al journal | `ListWorkflowRuns`/`GetWorkflowRun` devolvieron `workflow_introspection_unavailable` | §0 de este documento |
| «Run terminó» ≠ «hallazgo correcto» | Sin journal no hay veredicto por run; los `.mjs` son el programa, no el resultado | §0 |
| Creator end-to-end | El turno sin overlay no persistió el manifest. Con overlay sí (X3, ACTIVE, 19 artefactos), pero **antes** del arreglo del presupuesto: no valida el gate vigente | `docs/status.md` (§Pase integral, nº 2), `ensayo-x3-actualizado.md` |
| Ciclo de reparación íntegro bajo preset real | `x1-live` midió la provisión del Host y la obediencia del modo bajo headless; `x1-preset-real` cargó el preset y su skill pero se detuvo **antes de editar** por predicción de superar 120k tokens | `x1-live/RESULTADO.md`, `x1-preset-real/RESULTADO.md` |
| `git worktree add` real | Bloqueado por el sandbox de sesión; el diseño ya no lo usa, pero una sesión que actúe sobre lectura-escritura directa del canónico sigue sin probarse | `docs/status.md:210-226` |
| `dsh web` / endpoint evaluator / adaptador Host | `dsh web` **sí** arranca (home vacío, instalación real): el falso bloqueo se corrigió. No existe el endpoint `evaluator` en `0.2.0-rc.2`, y el CLI tampoco ofrece el adaptador que comprueba layout y skill efectiva antes de `session/create`: el runner se abstiene sin gastar | `docs/status.md:187-215`, `scripts/skill_gate_run.py:604-608` |
| Corpus completo contra modo real | Un caso de 55 falló con `NOT_COVERED`: compilaba una **skill** y despachó a un **modo** que exigía otro layout, y el modo no escribió `result.json`. Los 55 casos apuntan a 25 skills, no a los modos: no es una prueba del modo auditor | `corpus-fixed/RESULTADO.md`, `x3-corpus-live/RESULTADO.md` |
| `skill_router` contra sesión real | Sigue siendo solo selector informativo | `docs/status.md:9` |
| Confinamiento mecánico de bash en campaña | No se ejerció | `docs/status.md:9` |
| 26 de 30 stacks sin campaña | Declarados como hueco real de la beta | `docs/status.md:250` |

## 3. Cómo se mantiene este documento

- **Una lección, una prueba.** Una lección que dice tener prueba permanente
  apunta a `tests/test_workflow_lessons.py` con su identificador; si la prueba
  no está en el árbol, `DocumentedLessonsMapTests` falla.
- **Atribución obligatoria.** `test_lessons_map_at_least_a_run_id_or_a_commit_
  for_each_lesson` exige que cada fila nombre un run id, un sha, un `r-…` o una
  ruta. Sin atribución la fila no entra.
- **Nada local ni ajeno.** Las campañas corrieron en rutas del mantenedor y
  algún `.mjs` guardado contiene credenciales literalmente. Lo publicable es la
  lección, no el rastro: `test_no_local_paths_or_borrowed_identifiers_in_the_
  lessons_doc` rechaza rutas personales y material de terceros en este archivo.
- **Los `code fixes` de las lecciones viven donde el código vive.** Este
  documento documenta y prueba; no sustituye a `X1` ni edita `scripts/`,
  `README*`, `docs/status.md`, `CHANGELOG.md` ni `ARQUITECTURA_FLUJO_AGENTES.md`.
