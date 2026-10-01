# Plan de implementación y progreso

**Estado:** C0–C7, P1–P11 y las unidades de endurecimiento de los pilotos conservan verificación con evidencia recuperable; el trabajo abierto está en «Deuda declarada» y en las puertas G0–G6 del [plan de lanzamiento](docs/plans/10-lanzamiento-publico.md).
**Actualización:** 2026-09-27
**Fuente arquitectónica:** [ARQUITECTURA_FLUJO_AGENTES.md](ARQUITECTURA_FLUJO_AGENTES.md) v3.0

Este archivo es el único índice de progreso. Conserva tres niveles:

1. **Base MVP comprobada:** capacidades ya demostradas con DSH real, Syncify y RehabWeb.
2. **C0–C7:** implementación del flujo final de un comando: bootstrap → Creator automático → modos/skills específicos → validación/backup/aceptación Host → activación/rollback. Completadas.
3. **Post-C7:** hardening del flujo sobre evidencia real de pilotos en curso.

Los detalles históricos están en `CHANGELOG.md`; la evidencia privada, candidatos, sesiones y logs permanecen fuera del repositorio. Ningún documento o estado generado acredita por sí mismo ejecución.

## Estados

- `HECHO`: salida y gate comprobados con evidencia recuperable.
- `PARCIAL`: mecanismo o ensayo limitado; falta parte del gate.
- `PENDIENTE`: no implementado o sin evidencia suficiente.
- `BLOQUEADO`: requiere decisión, permiso o capacidad externa.
- `RETENIDO`: candidato preservado, pero no aceptado.

## Base MVP comprobada

| ID | Resultado | Estado | Evidencia principal | Límite conservado |
|---|---|---|---|---|
| B0 | Onboarding, skills, Host aislado y canal DSH | HECHO | `scripts/onboard.py`, `host_launcher.py`, `inference_channel.py`, presets fixture, tests; `docs/status.md` | No equivale al bootstrap Creator 3.0 |
| B1 | Auditoría, reparación, QA y reauditoría reales | HECHO | ciclos Syncify/RehabWeb; `missions.py`, `publisher.py`; ramas `workflow-repairs` | Unidades de producto RETAINED no se presentan como reparadas |
| B2 | Controlador, presupuesto, memoria y métricas | HECHO | `host_controller.py`, `budget.py`, `decisions.py`, `metrics.py` y regresiones | Descendientes remotos/pérdida física de energía limitados |
| B3 | Plugin de escritura y distribución privada por red | HECHO | `workflow-write`, clean-room remoto, regresiones | Plugin necesita empaquetado portable en C4 |
| B4 | MVP del núcleo fail-closed en dos proyectos | HECHO | 17/17 unidades con estado, archivos restaurables, `docs/status.md` | Acepta el framework, no declara productos libres de defectos |

## Etapas vigentes C0–C7

| ID | Resultado de salida | Estado | Trabajo principal | Gate de salida |
|---|---|---|---|---|
| C0 | Contratos generacionales, biblioteca y catálogo | HECHO | Schemas de run/manifest/project/capabilities/modes/skills/tests/handoffs/drift; biblioteca base inmutable; catálogo de patrones especializados; fixtures válidos/inválidos; procedencia MIT | Validador procesa corpus positivo/negativo y demuestra que Creator selecciona base/catálogo antes de proponer extensiones |
| C1 | `bootstrap install` determinista | HECHO | Preflight DSH/proveedor/Creator; workspace; generation-id; snapshot/authority; skills generales; prompt/paquete Creator; checkpoint/reanudación | Clone limpio prepara run completo sin modificar producto/config global |
| C2 | Automatización DSH Creator | HECHO | Sesión DSH Creator real con preset cordis ejecutada; generó paquete específico completo y ejecutó bootstrap.py accept | Un comando genera paquete específico válido y demuestra por qué no usa capas de reutilización antes de generar extensión |
| C3 | Validador Host de generación | HECHO | Validador independiente de 10 capas ejecutado sobre paquete real de C2; veredicto READY_FOR_ACCEPTANCE | Corpus negativo falla cerrado antes de cualquier backup/escritura activa |
| C4 | Backups, instalación transaccional y desinstalación | HECHO | Backup verificado, staging, swap atómico y rollback verificados sobre el paquete real | Fallos inyectados nunca dejan conjunto mixto; estado anterior restaurable |
| C5 | Aceptación automática DSH | HECHO | Creator invocó accept; Host ejecutó validación estática, ledger de evidencia y veredicto fail-closed | Creator invoca `accept`; solo Host emite ACTIVE o RETAINED/rollback |
| C6 | Piloto clean-room en proyectos nuevos | HECHO | Pilotos clean-room ejecutados en proyecto Python/backend y proyecto multiparte (Python+TS) con DSH real, métricas, rollback y uninstall | Usuario con DSH/proveedor configurado obtiene modos específicos con un comando |
| C7 | Promoción y distribución de piloto | HECHO | Reconciliación de runs ejecutada; THIRD_PARTY_NOTICES.md (MIT) añadido; preparación y publicación verificadas | Repo enlazable para testers, versión fijada y clean-room repetible |

## Post-C7 — hardening sobre piloto real

Unidades posteriores a C7, cada una con cambio de flujo, regresión y entrada en `CHANGELOG.md`:

| ID | Resultado | Estado | Contenido comprobado |
|---|---|---|---|
| P1 | Registro de fuentes y biblioteca materializada | HECHO | 43 fuentes con procedencia fijada (commit o spec_version); 21 skills base inmutables y 4 patrones de catálogo con criterios de activación y escenarios; regresión bidireccional |
| P2 | Integración biblioteca ↔ Creator | HECHO | snapshot de biblioteca por run, prompt con base/catálogo, `reuse_reference` resuelto por el validador Host contra el snapshot |
| P3 | Despacho automático y ciclo de vida DSH | HECHO | detención de instancias previas, propiedad del puerto, cookie HMAC del home, lanzamiento no interactivo con diagnóstico, resolutor de proveedor utilizable |
| P4 | Sesión Creator ligada al workspace | HECHO | `workspace/create` + `workspaceId`; única sesión Creator, agrupada en la UI, sin sesiones evaluator/reviewer ni delegación; frontera `workspace-write` = workspace del run |
| P5 | Política anti-escalada de sandbox | HECHO | plugin del framework: campos de escalada fuera de los schemas de tools, escalada de bash guardada, mismo-modo corregido en `workflow_write` (overlay `dsh web --patch`); prompt prohíbe el canal completo |
| P6 | Transacción con veredicto Host | HECHO | `install` exige veredicto ACTIVE explícito de la misma generación antes de activar |
| P7 | Aceptación Host aislada del Creator | HECHO | harness del Host con evaluador y revisor aislados, casos ocultos con predicados privados, cardinalidad completa, actores correlacionados con turnos DSH reales |
| P8 | Instalación de modos como presets DSH | HECHO | bundle de declaraciones `@deepseek-ai/dsh-agent-preset` instalado por `pluginManager/installBundle`, con roster verificado vía `agentPresets/list`; `READY_FOR_INSTALL` determinista antes de `ACTIVE` |
| P9 | Gate operativo y ruta real de skills | HECHO | cada modo exige persona+bash+fs+fs-search (`sampleOverCapGlobResults: false`)+skill-filesystem+tool-skill y rechaza delegación/workflow/web/plugin-manager; frontmatter mínimo validado; bundle copia skills/recursos y skills de modo, con root local exclusivo y recibo de ambos presets |
| P10 | Piloto tardis (Syncify) con DSH real | HECHO | 77 hallazgos distintos (114 registros) atendidos por los modos con handoff y verificación; integración solo por commit/fast-forward/push del operador y CI verde en 3 jobs en `b9413eb`. El registro de cierre declara D-01..D-04 como alcance condicionado (SoundCloud/Apple Music dependen de credenciales del propietario), no como trabajo pendiente |
| P11 | Handoff durable y reparación acotada | HECHO | bootstrap exacto de skill, schemas/caps, migración preflight por digest, candidato determinista registrada antes del primer cambio, commit no implícito e invariantes canónicas, con regresiones. Ejercitado con DSH real en tres campañas posteriores (RehabWeb, LoboApp y el self-test del framework). Dos límites siguen sin implementar y son deuda declarada, no parte de esta unidad: el confinamiento mecánico de bash y el CAS/lease multiarchivo |

Suite de regresión vigente: ver último registro en `CHANGELOG.md`; la suite completa corre en verde antes de cada cierre de unidad.

## Deuda declarada

Trabajo abierto con evidencia detrás, no sobre el papel. Cada línea es una unidad
pendiente con su criterio de cierre; ninguna está implícita en otro estado `HECHO`.

| ID | Qué falta | Estado | Cierre |
|---|---|---|---|
| D1 | CAS/lease o escritura atómica multiarchivo de `mode-state` | HECHO 2026-10-01 | Lease por fichero con TTL de 30 s: cierra el reemplazo concurrente del mismo fichero. La atomicidad del lote de cinco ficheros **no** se cierra —el backend no ofrece transacción— y sigue declarada en `write_method` |
| D2 | Confinamiento mecánico de bash del auditor | HECHO 2026-10-01 | **Medido contra `0.1.7-rc.2` instalado, no deducido.** `dsh-sandbox-policy` resuelve `workspaceRoot` desde el cwd de sesión, y ese es el error: la raíz escribible era el **padre** del producto y del workspace, así que `workspace-write` dejaba clobberar el producto tanto por bash como por `ctx.fs` (verificado: contenido del producto pasa a `CLOBBERED`). **Apuntar la política al workspace en vez de a la raíz de sesión lo resuelve**: el producto queda fuera de `writableRoots()`, la bash recibe `EROFS` real ("Read-only file system"), los descendientes heredan la frontera, y las escrituras de estado del auditor **siguen funcionando** — tanto por bash como por `ctx.fs.writeText`. La premisa anterior era cierta en su hecho y falsa en su conclusión: `read-only` sí niega toda mutación de `ctx.fs` (comprobado), pero no hace falta `read-only`; `workspace-write` sobre una raíz mas estrecha da lo que se buscaba sin negar el estado. **El reparador sigue bloqueado, y por una razón medida que no se había aislado:** `writableRoots()` admite **una sola** raíz configurable (`dsh-sandbox/lib/index.js`), y el reparador necesita dos —su candidata y el estado compartido—. Rozar la política a la candidata deja el producto en solo lectura pero niega `mode-state`; y `git worktree add` registra el worktree en el `.git` **del producto**, que ahora es de solo lectura, así que una sesión confinada no puede aprovisionar su propia candidata (`git_exit=255`). Cerrarlo exige que el Host aprovisione la candidata fuera de la sesión confinada, no un parche de política. Todo ello queda fijado en `tests/test_auditor_confinement.py` contra el runtime real, con negativos: raíz en la sesión = 5 pruebas fallan, `read-only` = 2 fallan |
| D3 | Gate de reconteo `persisted_count` contra el fichero | HECHO 2026-09-30 | `count_command` central que recalcula el conjunto abierto desde el fichero e imprime el número; el handoff debe cubrir exactamente ese conjunto y `workflow_write` lo rechaza si no |
| D4 | Aviso y re-apuntado asistidos ante reescritura de commits tras integrar | HECHO 2026-09-30 | `bootstrap.py state` lo detecta (`integrated_head_rewritten`) y `--repoint` solo acepta revisión ancestro del HEAD canónico con producto limpio, con recibo en `overflows.jsonl` |
| D5 | Retirada de candidata como mecanismo verificado, no procedimiento | HECHO 2026-09-30 | `bootstrap.py state --retire` verifica condición por condición y es idempotente; el procedimiento manual de `docs/usage.md` queda como explicación, no como paso |
| D6 | Enum de `verification-results`: `PARTIAL` entra o se exige enum cerrado con N/A justificado | DECIDIDO 2026-09-30 | El enum sigue cerrado y `PARTIAL` pasa a ser veredicto **derivado** por hallazgo (peor resultado gana: FAIL > BLOCKED > PASS), con un registro por entrypoint; `REPAIRED` no entra |
| D7 | Hallazgo rico (fingerprint, causa, prevención de recurrencia) en `mode-state` | HECHO 2026-09-30 | `evidence.path`+`excerpt` con `line`, `located` y `fingerprint` calculados por la herramienta; `cause` y `prevention` acotadas a 256 B y el cap de 4.096 B del registro comprobado en el límite de escritura; reparto `anchors` en `bootstrap.py state`. Los tres campos nuevos son opcionales, así que la evidencia histórica no se archiva |
| D8 | Vista derivada de hallazgos cerrados por work item VERIFIED | HECHO 2026-09-30 | `bootstrap.py state` nombra `closed_findings` y `uncovered_findings` sin reescribir el ledger |
| D9 | Directorio de evidencia fuera de `mode-state` para parches y logs grandes | HECHO 2026-09-30 | Raíz gestionada `<workspace>/evidence` con topes propios (8 MiB/fichero, 256 MiB, 200 ficheros, nombre seguro) y recibo en `overflows.jsonl` al descarter; `workflow_write` la acepta y sigue negando todo lo demás |
| D10 | Plantilla que distinga auditoría completa de incremental (anti-anclaje) | HECHO 2026-09-30 | `audit_scope` en el contrato y la persona: en completa se observa antes de leer la cola, en incremental se parte del diagnóstico; el alcance viaja en el `handoff_id` y `bootstrap.py state` cuenta ambos |
| D11 | Paquete de memoria F5, RSI y disparador por commit | HECHO 2026-10-01 | **El mecanismo ya es ejecutable; sigue faltando la ejecución.** `scripts/corpus_compiler.py` compila los 55 escenarios de `library/` en casos ejecutables deterministas (`task` + fixture + `evaluated_claim`, reutilizando `acceptance_harness._public_input`), ligados por `source_digest` y `corpus_digest`; `bootstrap.py compile-corpus` lo produce y `bootstrap.py bound-skill-gate` puntúa contra él. **El oráculo no viaja en el caso público**: `expected_verdicts` se deriva en el Host y solo acepta un corpus cuyo digest recalculado coincida con el declarado — un corpus editado después de compilar se rechaza, y esa comprobación la añadió una regresión que encontró el hueco. Las observaciones van ligadas a corpus, candidato y versión de compilador, y un proveedor `unavailable` no puede declararlas. `bootstrap.py skill-gate-commit-check` exige un informe ligado y aceptado cuando cambian `library/` o el propio gate, y **abstain bloquea igual que reject**: la abstención no es permiso. Las cuatro decisiones del gate se ejercitan contra el corpus real (accept, reject por no mejorar, reject por regresión en entrenamiento, abstain) con 27 regresiones, cada una comprobada rompiendo lo que protege. **Lo que sigue abierto y por qué:** ningún cambio de biblioteca ha pasado aún por el gate con observaciones de un agente real, porque ejecutar el corpus necesita un proveedor configurado por el operador —el framework no lo instala ni lo invoca—. El disparador por commit existe como comando explícito para un hook o CI, no instalado como hook. F5 (memoria episódica e índice) es E2 y está cerrada; lo que sigue abierto es su ejecución, no su diseño |
| D12 | Publicación de la beta (tag y push) | HECHO 2026-09-30 | G6 cerrada con autorización del titular: tag `v0.1.0-beta` y `dev` publicado; notas en `docs/plans/11-notas-beta-v0.1.0.md` |
| E1 | Commit transaccional de `mode-state` (D1 cerrado) | HECHO 2026-10-01 | Un marcador de escritura anticipada en `mode-state/.commit.json` nombra la unidad y cada par (ruta, digest) que va a aterrizar; el marcador se borra al cerrar la unidad y, si aparece colgando, la reconciliación de arranque declara la unidad RETAINED nombrando qué ficheros sí quedaron. **Decisión propia:** la atomicidad multiarchivo real es imposible sin un almacén de fichero único, y la alternativa a detectarla —ignorarla— es lo que produce estado inconsistente en silencio. Se compra detección y recuperación, y se declara que no es atomicidad |
| E2 | Memoria episódica e índice (F5 cerrado) | HECHO 2026-10-01 | `mode-state/episodes.jsonl` con un registro por unidad cerrada —firma del defecto, clase, arreglo que funcionó y verificación que lo probó— más `mode-state/episodes-index.json` que mapea firma a ids para consulta O(1) sin cargar el log. Solo el Host escribe el log; el modo lo lee y **tiene que consultarlo antes de persistir un hallazgo**, marcando las repeticiones con el episodio previo. **Decisión propia:** sin esto el auditor vuelve a reportar el mismo defecto cada sesión, que es el fallo de memoria más caro que tiene este framework |
| E3 | Ejecutor del gate de biblioteca (D11 cerrado en código) | HECHO 2026-10-01 | `bootstrap.py skill-gate-run` corre cada caso compilado contra un modo real usando el canal de inferencia del Host y escribe observaciones ligadas; sin proveedor configurado se abstiene nombrando lo que falta. **Decisión propia:** la corrida con credenciales es del operador y no se puede fabricar, pero el camino hacia ella sí es código del framework y faltaba |
| E4 | Confinamiento del reparador (D2 cerrado) | HECHO 2026-10-01 | La candidata deja de ser un *worktree* del producto y pasa a ser un **repositorio sombra autónomo** con su propio `.git`, creado por el Host dentro del workspace. **Decisión propia, y está medida:** un worktree guarda índice y HEAD en el `.git/worktrees/` del producto, así que un producto con `.git` de solo lectura hace inusable `git add`/`git status` en la candidata —confinamiento y worktree son incompatibles—. Con el repo sombra, una sola raíz escribible cubre candidata y estado, y el producto queda en solo lectura real. La integración pasa a ser el diff que el operador aplica |
| E5 | Honestidad de la cobertura de stacks | HECHO 2026-10-01 | Para los siete stacks declarados pero no probados en campaña real (Node, Go, Maven, Gradle, .NET, PHP, Ruby), una regresión comprueba que el comando de verificación declarado **resuelve** contra un fixture mínimo de esa tecnología, y la documentación dice por stack si hay evidencia de campaña real o solo declaración. **Decisión propia:** un comando plausible escrito a mano no es cobertura, y la diferencia tiene que quedar visible para quien use la beta |
| E6 | Cerrar el bucle de lectura de la memoria episódica | HECHO 2026-10-01 | La auditoría de cierre encontró que E2 escribía `episodes.jsonl` y `episodes-index.json` pero ningún camino de producto leía el índice: la documentación decía «el auditor lo consulta» y el framework volvía a reportar el mismo defecto. `workflow_write` consulta ahora la firma exacta que él mismo calcula y estampa `evidence.prior_episode` cuando un arreglo ya verificado había cerrado ese código; un modo no puede autodeclararlo, índice presente e ilegible falla cerrado e índice ausente significa memoria vacía. `bootstrap.py state` hace visible la prevención fallida en `repeats`. Una regresión ejecuta ocho casos y fue canario-comprobada quitando la consulta; otra ata persona, contrato y plugin para que no vuelvan a divergir |
| E7 | El veredicto derivado se promete en tres sitios y no se calculaba en ninguno | HECHO 2026-10-01 | El plugin guardaba un registro por entrypoint y decía en su propio comentario que «el Host lo deriva»; el contrato declaraba `worst-result-per-finding-and-candidate-partial-is-derived-not-written` y la persona se lo decía al modo. `stack.derived_verdicts` existía, tenía regresión y **no la llamaba nadie fuera de `tests/`**: un hallazgo verificado en parte no tenía veredicto en ninguna parte. Ahora `state` lo deriva en lectura y añade `partial`, que el veredicto desnudo tiraba: `BLOCKED` con un PASS y un BLOCKED es progreso, `BLOCKED` con un solo BLOCKED es no haber corrido nada |
| E8 | El ledger de métricas se escribía y nadie lo leía | HECHO 2026-10-01 | El controlador registra un evento `turn` por unidad cerrada; `metrics.summarize` y `metrics.verify` tenían seis regresiones y ninguna llamada. `bootstrap.py metrics --mission` verifica la cadena **antes** de agregar —un total sobre un ledger manipulado no es una medición— y declara `NO_DISPONIBLE` lo no registrado, nunca cero, porque cero afirmaría que la misión costó nada |
| E9 | La mitad de reflexión del RSI | HECHO 2026-10-01 | El gate rechazaba, imprimía la razón y la tiraba: el siguiente intento partía de cero y pagaba una corrida completa de agente para recibir la misma respuesta. `scripts/reflection.py` guarda el rechazo con su holdout antes y después, `bound-skill-gate --buffer` lo registra, **reenviar una candidata ya rechazada contra el mismo corpus se niega sin puntuarla**, y `skill-gate-reflect` da el resumen que debe leer el siguiente intento. Un rechazo de otro corpus no aplica: respondió a otra pregunta |
| E10 | La cobertura de stacks no era falsable | HECHO 2026-10-01 | Dos pruebas de `docs/status.md` solo comprueban que cuatro cadenas aparezcan cerca de un encabezado, con el conjunto probado hardcodeado en el cuerpo del test: **editar el documento para afirmar una campaña que no ocurrió las dejaba verdes**, y un stack nuevo en el registro no tenía que aparecer en la tabla. `stack.CAMPAIGN_EVIDENCE` declara la evidencia junto a los comandos y las pruebas ahora exigen las dos direcciones —probada con su campaña, declarada sin ella. Canario: falsificar Go en el documento rompe la suite |
| E11 | La cuenta que se publica no decía qué no se ejecutó | HECHO 2026-10-01 | «NNN pruebas en verde» sin más cubre once regresiones que no corren sin `DSH_MODULE_ROOT`, `node`, `bubblewrap` o `jsonschema`. `docs/status.md` nombra cada componente y qué se pierde con él, y una regresión comprueba que **ningún `skipTest` del repo puede existir sin nombrar un componente que el repositorio no distribuye** |
| E12 | Comandos que funcionaban y nadie encontraba | HECHO 2026-10-01 | `audit.py archive`, `missions.py reaudit`, `transaction.py install\|rollback\|uninstall` y `skill-gate-run` no estaban en `docs/usage.md`. Documentados como superficie de servicio, con `metrics` y `skill-gate-reflect`. La regresión recorre los `add_parser` del repo, así que un subcomando nuevo sin documentar falla ahí |
| E13 | El contrato emitido no se validaba contra su schema | HECHO 2026-10-01 | La prueba de presupuesto construía el documento `mode.json` para medir bytes y ahí acababa. Ahora se valida contra `schemas/modes.schema.json` con `generation_contracts.validate("mode-contract", …)` para los dos roles, y la comprobación se prueba no vacía con un `candidate_root` que el schema prohíbe — la deriva exacta que rompió la aceptación cuando `candidate_location` se quedó desincronizado |
| E14 | Código huérfano y readers duplicados | HECHO 2026-10-01 | Análisis AST sobre `scripts/`: `stack.derived_verdicts`, `stack.validate_verification_results`, `stack.allowed_verification_commands`, `metrics.summarize`, `metrics.verify`, `episodes.stats` y `episodes.read_episodes` no los llamaba ningún camino de producto. Los siete están cableados. `episodes.is_repeat` se **elimina**: con E6 el lector es el plugin, y un segundo lector sin llamantes es una segunda fuente de verdad |
| E15 | La única declaración real del repositorio estaba fuera del invariante que la suite prueba | HECHO 2026-10-01 | `test_stack_coverage` demuestra que «plan listo ⇒ comando ejecutable» para once productos sintéticos, y el `improvement-verification.json` del propio framework —la única declaración que se publica— no lo resolvía ninguna prueba. `stack.declared()` valida forma, no ejecución, así que un comando truncado seguiría resolviéndose `verification_ready: true`. Ahora la prueba resuelve el plan del repositorio y lanza su comando: valen tanto salir en verde como seguir corriendo a los diez segundos, y morirse en el argv no vale. Canario: el mismo comando sin su último argumento |
| E16 | Ningún schema decía quién lo aplicaba | HECHO 2026-10-01 | Diecinueve de veintidós eran alcanzables por el registro de `generation_contracts`; los tres contratos del corpus los aplicaba un validador a mano en `corpus_compiler` al que nada apuntaba, y dos de los demás se direccionaban con un nombre que no era el de su archivo (`mode-contract` para `modes.schema.json`). `SCHEMA_VALIDATORS` declara la unión en el producto, `schema_enforcement()` la resuelve y `validate()` admite las dos grafías; la regresión exige biyección exacta con `schemas/`. Canario: un schema suelto rompe la suite |
| E17 | La cuenta de la suite se llevaba a mano | HECHO 2026-10-01 | «743» y «755» a dieciséis líneas en el README, sin decir cuál era vigente. La cuenta ahora se descubre con `TestLoader().discover(...)`, y una cifra que no coincide tiene que declararse de otro momento («en ese punto»). Canario: 760 → 799 en el README |
| E18 | Los fixtures dorados no los leía nadie | HECHO 2026-10-01 | `fixtures/README.md` afirma que sus golden manifests validan generadores y validadores y que no llevan rutas ni credenciales; nada abría `fixtures/`. Los cuatro manifiestos se validan ahora contra `generation-manifest` y `project-manifest` en cada corrida, con no-vacuidad (quitar un campo obligatorio los hace fallar), y el saneado y la regla de no instalación son mecánicos |
| E19 | El instalador de skills perdía skills en silencio | HECHO 2026-10-01 | `prepare_project_skills` seleccionaba directorios por la presencia de `SKILL.md` y copiaba sin parsear: frontmatter ilegible o nombre distinto del directorio se instalaba y no lo descubría nadie, y un directorio con contenido sin `SKILL.md` se perdía sin aparecer en el resultado — lo que la arquitectura prohíbe para el preflight. Ahora falla cerrado nombrando el directorio y valida el frontmatter; un directorio vacío se deja pasar. Las cinco skills reales se comprueban ellas mismas. La prueba previa usaba una skill con saltos de línea literales que solo pasaba porque nadie la leía |
| E20 | La atribución se quedaba a un paso del aviso público | HECHO 2026-10-01 | Cada una de las 25 skills declara en su `## Procedencia` de qué upstream se adaptó, y `test_attribution_present` se satisfacía con la palabra «MIT». `THIRD_PARTY_NOTICES.md` nombraba un solo upstream mientras `docs/status.md` afirmaba que la atribución MIT de `obra/superpowers` y `addyosmani/agent-skills` ya estaba hecha. Los dos upstreams, con su revisión fijada, su licencia y su texto MIT, están ahora en el aviso, y la regresión exige upstream **y** revisión para todo lo que la biblioteca declara. Canario: recortar la revisión en el aviso rompe la suite |
| E21 | La regla del árbol canónico no la comprobaba nadie | HECHO 2026-10-01 | `AGENTS.md` exige que los artefactos de ejecución vivan fuera del repositorio y dice que ignorarlos en Git no basta; solo había `.gitignore`. `tests/test_canonical_tree_holds_no_run_artifacts.py` falla por nombre ante cualquier fichero o directorio de run dentro del árbol, con el vocabulario tomado de los literales de `scripts/` —y un segundo test relee esos literales y exige que el inventario los cubra, que es como aparecieron `evidence-ledger.jsonl` y `scenarios.jsonl` en la primera corrida—. `fixtures/` queda exento por diseño y sujeto a su propia regla de saneado. Canario: plantar `mode-state/work-items.json` |
| F5B | Índice local del codebase (capa B del borrador) | DECLINADO 2026-10-01 | Tres motivos medidos, en `docs/external-orchestration-draft.md`: duplica el alcance que `dsh-tool-fs-search` ya da a todo modo generado; sus dependencias (`tree_sitter`, `sqlite_vec`, `fastembed`, `onnxruntime`) no son distribuibles en este árbol; y su propio invariante —«el índice es un localizador, no prueba de nada»— lo saca del árbol de lo que el framework acierta. **Lo que cambia la decisión:** una campaña que mida tokens de navegación por encima de lo que `fs-search` cubre, y entonces se construye por la estructura de símbolo que a los modos les falta |

## Dependencias

```text
C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7
          └──── discovery/design/test/generation internos ────┘
```

C0 puede preparar fixtures, schema y validadores en paralelo. C4 puede diseñarse mientras C2 avanza, pero no se acepta hasta que C3 valide un paquete real. C6 debe arrancar desde clon y DSH con proveedor ya configurado, no desde imagen preconfigurada.

## Capacidades internas de Creator

No son modos finales del usuario:

```text
creator-project-discovery          (audit)
creator-project-documenter         (document)
creator-contract-and-risk-mapper   (audit + architect)
creator-capability-partitioner     (scope)
creator-capability-designer        (architect)
creator-scenario-author            (test)
creator-skill-generator            (develop)
creator-generation-repair          (debug)
creator-drift-analyzer             (sync)
```

El resultado final por proyecto sigue siendo:

```text
<Proyecto>-auditor
<Proyecto>-continuous-repair
+ skills específicas justificadas
```

## Reglas de actualización

1. Solo se marca `HECHO` con evidencia recuperable y negativos pertinentes.
2. Un cambio material de diseño actualiza primero `ARQUITECTURA_FLUJO_AGENTES.md`.
3. No importar perfiles, candidatos, rutas privadas, sesiones o logs al repo.
4. Creator nunca puede cerrar su propia etapa como aceptada.
5. Backup presente no equivale a rollback comprobado.
6. Schema válido no equivale a skill útil ni segura.
7. El historial de C0–C7 va en Git/CHANGELOG, no como diario en la arquitectura.
