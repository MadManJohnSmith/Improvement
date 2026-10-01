# Cambios

## Las 51 comprobaciones del self-check ya no son código muerto — 2026-09-30
- `verify-workflow-write.mjs` **no lo invocaba nadie**: 51 checks —integridad del plan de capacidades, estrictez de schema, denegaciones del sandbox, y el barrido M7/M9 de escalada— que solo se ejecutaban a mano. Un script de verificación que nadie corre se pudre en silencio, y este respaldaba justo las afirmaciones de seguridad del repositorio.
- **Al arreglar la ruta del mantenedor en la entrada anterior se había introducido una pérdida de alcance**, y se corrigió aquí: el script pasó a fallar cerrado sin `DSH_TOOL_BASH`, con lo cual **los 32 checks que solo necesitan node nunca llegaban a ejecutarse**. Ahora el barrido M9 es un bloque condicionado: sin runtime imprime `SKIP` y los otros 33 se siguen corriendo. Perder verificación por una variable de entorno ausente sería exactamente el `skip` que esta serie de commits lleva eliminado.
- Una regresión nueva lo ejecuta dentro de la suite y exige al menos 33 `PASS`, con lo que los 51 dejan de ser código muerto. Se comprobó en las dos direcciones: **con runtime los saltados bajan de 4 a 2** y la prueba corre; y al forzar un check a fallar la prueba falla, luego no es vacía.
- Suite: 632 OK (4 saltadas sin runtime, 2 con `DSH_MODULE_ROOT`).

## Auditoría de los `skip`: solo dos ocultaban defectos — 2026-09-30
- Un `skip` que se activa por defecto no es una prueba, es una ausencia de prueba, y ya demostró que puede esconder un bug real. Se revisaron **las doce** declaradas en la suite en vez de dar por bueno el resto. Resultado: **solo dos** ocultaban algo —las dos de runtime vivo de la entrada anterior—. Las demás se ejecutan de verdad en esta máquina.
- Las siete de `test_workflow_write_plugin.py` que dependen de `node` **corren** (`node` está en el PATH) y la de reinicio de Host en `test_recovery_durable.py` **también**, porque bubblewrap está instalado. La de paridad JSON Schema se salta por `jsonschema` ausente, que es una dependencia opcional legitimí1a: se comprobó su contenido a mano y **las tres validadores coinciden** en los cuatro casos (plan válido y los tres campos con `" \t"`), así que el `skip` no esconde una discrepancia.
- Lo que se registra no es que todo esté bien, sino que el único sitio donde un `skip` podría estar callando algo ya no lo está: cada uno de los doce se ejecutó o se justificó con su razón.

## Dos pruebas vivas estaban rotas y el `skip` lo tapaba — 2026-09-30
- **La suite se declaraba en verde sin haber probado nunca lo que dice probar.** Las dos únicas pruebas que levantan el runtime DSH real están saltadas por defecto (`DSH_MODULE_ROOT` no viene puesto), así que su verde no dice nada sobre ellas. Al ejecutarlas contra el runtime instalado aparecieron **dos bugs reales**.
- **`ctx.shell.execute` no existe en ninguna versión publicada de DSH.** `ShellExecutor` es una clase abstracta con un getter `sandboxMode`, y el ejecutor concreto (`dsh-bash-local`) expone `resolve`, `run` y `start`, jamás `execute`. La prueba llamaba a un método que nunca existió, así que nunca pudo pasar. Corregida a la API real: **ahora se ejecuta y pasa**, y con ello el repo prueba por fin lo que afirmaba — que el producto queda intacto ante un intento de escritura y que un proceso descendiente también queda bloqueado, contra bwrap de verdad y no contra un mock.
- **La otra falla por versión, no por código, y ahora lo dice.** `verify-workflow-write.mjs` no lo invoca nadie — 45 comprobaciones, incluidas las de M7/M9 que respaldan el bloqueo de escalada, que solo se ejecutan a mano. Sus dos rutas al runtime las daba el mantenedor (arreglado en la entrada anterior), y además fijaba `lib/profile-boot.js`, un nombre que **sólo existe desde 0.2.x**: el runtime instalado (`0.1.5-alpha.1`) solo trae chunks con hash. Ahora resuelve el entrypoint disponible. La prueba que lo monta usa `@deepseek-ai/dsh-agent-preset`, que **no se publica hasta 0.1.7-alpha.1**, así que con este runtime no puede correr: el `skip` ahora nombra la versión que hace falta en vez de fallar con un `ERR_MODULE_NOT_FOUND` que no explica nada.
- Lo que **no** se tocó: el nombre del paquete. Cambiarlo a `dsh-agent-presets` (que sí existe instalado) parece el arreglo, pero ese plugin es otro servicio —el de autoría y roster, que exige `default` y `roots`—, no el registro de un preset por agente. Habría sido un arreglo falso: la prueba volvería a fallar por configuración en vez de por la razón real.
- Suite: 631 OK (3 saltadas).

## La ruta local del mantenedor salió en un archivo publicable — 2026-09-30
- `scripts/dsh-plugins/verify-workflow-write.mjs` **usaba como valor por defecto la ruta absoluta del checkout del mantenedor** en dos sitios (`DSH_TOOLS_INDEX` y `DSH_TOOL_BASH`). Eso rompe la regla del repo de no llevar rutas locales en archivos publicables, y además rompe en silencio para cualquiera que no sea el autor: el script nunca hubiera encontrado el runtime en otra máquina. Ahora ambas rutas las declara quien lo ejecuta y, si faltan o no existen, el script **falla cerrado** en lugar de seguir.
- La regresión comprueba lo mismo que se rompió, pero sobre **los ficheros que Git publica** en vez de solo prosa: antes solo se miraban siete documentos. Al escribirla detectó que mi propio `.zcode/` — scratch de la app, ignorado por Git — contenía cuatro ficheros con la ruta, lo que confirmó que el defecto era real y no solo teórico.
- Verificado en las dos direcciones: el script **falla cerrado** sin las variables, y con ellas ejecuta sus 45 comprobaciones contra el runtime real y termina en `TODO OK`.
- Suite: 631 OK (3 saltadas).


## D11 no esperaba un runtime: los escenarios no son ejecutables — 2026-09-30
- **D11 estaba bloqueada por la razón equivocada.** Decía que faltaba «correr los 55 escenarios contra un modo DSH real». Comprobarlo muestra un obstáculo anterior: **los 55 escenarios de `library/` no se pueden ejecutar tal cual**, ni con runtime. Su `input` es una tabla de aserciones **declarativas** sobre una situación —`contract_declared: true`, `attempted_write: true`, `direct_git_mutation: true`— y no una tarea que un agente pueda recibir. Los ficheros no llevan `target_mode` ni prompt, y **solo uno de los 55** tiene siquiera un campo `task`. Son una especificación de qué debería observarse, no un caso ejecutable.
- Esto cambia qué significa cerrar D11: no basta con ejecutar un modo real y leer una puntuación, porque **no hay nada que ejecutar**. El gate (`scripts/skill_gate.py`) está bien construido y es correcto —reparto determinista, aceptación solo por mejora estricta, rechazo por regresión en entrenamiento, abstención sin evidencia— pero sus entradas las produce alguien de fuera, y hoy ese alguien no puede producirlas. El orden real es: dar forma ejecutable a los escenarios, y solo entonces el runtime deja de ser el bloqueo.
- Para que conste con precisión, porque se comprobó en vez de suponer: el runtime DSH **sí** está instalado en esta máquina y el endpoint de modelos **sí** responde, así que la infraestructura no es lo que falta. Lo que falta es que el corpus sea ejecutable.
- **Añadido lo que hace falta para cerrarla, y sale más barato de lo que parecía:** la forma ejecutable ya existe en `acceptance_harness._public_input`, que materializa la misma idea con `task`, fixture acotada y `evaluated_claim`, y su vocabulario de tipos cubre **los 8** que usa este corpus. Los dos corpus están desconectados —fuera de `skill_gate` nada lee `library/`, y el harness genera sus propios casos Host—, así que unirlos es trabajo de autoría sobre una plantilla probada y no maquinaria nueva. Se verificó comparando ambos vocabularios: 8 de 8 coinciden.
- Suite: 630 OK (3 saltadas).

## La premisa de D2 era falsa, y el bloqueo real es otro — 2026-09-30
- **La fila de D2 afirmaba que el servicio de política del runtime solo expone `mode` y `workspaceRoot`, sin un modo de solo lectura comprobable, y que hacía falta el runtime instalado para averiguarlo.** Es falso, y esta entrada lo corrige con evidencia en vez de suavizarlo. El runtime DSH está instalado (`0.1.5-alpha.1`) y trae el confinamiento mecánico completo: `dsh-sandbox-policy` con `read-only`, `workspace-write` y `danger-full-access`, con `read-only` como **default fail-safe**, más `dsh-bash-sandbox` y `dsh-fs-sandbox` sobre bwrap en Linux, Landlock donde no hay bwrap y Seatbelt en macOS.
- **La denegación es real y se comprobó en esta máquina, no de palabra:** un `bwrap` con la raíz de la sesión enlazada en escritura falla al escribir en el producto con `Read-only file system` y el fichero de destino queda intacto. Eso es un `EROFS` del kernel que el comando no puede discutir, que era exactamente lo que la fila decía que no se podía tener.
- **El bloqueo que queda no es de capacidad sino de diseño, y por eso D2 sigue abierta.** Un modo **no puede declarar su propia política**: `dsh-agent-presets` rechaza que una fila de preset publique un servicio global, así que `sandboxPolicy` es de la composición anfitriona y el modo solo la hereda. Y `read-only` no resolvería el caso del auditor aunque pudiera declararlo, porque `checkedTarget` deniega **toda** mutación de `ctx.fs` y sus propias escrituras de estado pasan por `workflow_write` → `ctx.fs.writeText` con la política resuelta: auditaría y no podría persistir nada. Queda `workspace-write`, que deja escribir el producto, porque la raíz escribible es el **cwd de sesión** y el producto es hermano del workspace *dentro* de ese cwd.
- Se comprobó también el límite que condiciona cualquier solución: **`git worktree add` escribe dentro del `.git` del producto**, así que con el producto en solo lectura la candidata no se puede provisionar. Cerrar D2 exige mover el producto fuera de la raíz escribible —un cambio de layout, no de política— o un canal de escritura que no pase por `ctx.fs`. Ninguna de las dos cosas cabe en un parche de composición, y esta entrada no presenta el hallazgo como cierre.

## Cierre de la deuda declarada — 2026-09-30
- Ocho unidades sobre la tabla de deuda que el propio repo carryaba, cada una con regresión y suite en verde: D3 recuento de la auditoría, D4 reescritura de commits, D5 retirada de candidata, D6 veredicto derivado, D7 hallazgo rico, D8 vista de cierre, D9 raíz de evidencia, D10 alcance de auditoría, D1 lease por fichero y el gate de holdout de D11.
- **Queda abierta D2** y no por falta de trabajo: el confinamiento mecánico de bash no se cerraba aquí, y una lista negra de comandos no es confinamiento. La fila lo dice con esas palabras para que nadie la lea como un olvido. *(La razón que daba —"hace falta el runtime DSH instalado"— era falsa y está corregida en la entrada de arriba: el runtime está instalado y sí confinementa; el bloqueo real es de diseño.)*
- **D11 queda a medias con honestidad**: el gate está implementado y probado contra observaciones sintéticas, pero ejecutar los 55 escenarios contra un modo real —lo que convertiría la tabla en puntuación — no se ha hecho, así que ningún cambio de biblioteca ha pasado por él todavía.
- **D12 y G6 siguen bloqueados por autorización del titular**: el tag `v0.1.0-beta` y la publicación no se han hecho. El árbol tiene diez commits locales por delante de `origin/dev` y cero tags.

## El gate que decide si una skill merece entrar — 2026-09-30
- **El corpus tenía 55 escenarios con veredicto esperado y nadie los ejecutaba.** La regresión comprobaba que cada skill tenga un positivo y un negativo, nunca qué pasó al correrlos: sin eso, un cambio de skill es indistinguible de una mejora. `scripts/skill_gate.py` más `bootstrap.py skill-gate` es esa decisión y nada más — las observaciones entran desde fuera, porque correr escenarios contra un agente necesita un runtime.
- Tres propiedades tomadas de SkillOpt porque son fáciles de hacer mal: el candidato se acepta **solo** si mejora estrictamente el holdout —igual no es mejor, y «no peor» es como se filtra una regresión—; se rechaza aunque el holdout suba si pierde en la partición de entrenamiento, que es la forma de un sobreajuste; y si el slice de validación no es disjunto o no hay observaciones, el gate **se abstiene** en vez de pasar o suspender. Abstención y rechazo son cosas distintas: lo primero no tiene evidencia para juzgar, lo segundo la tiene y el candidato sale perdiendo.
- El reparto es determinista —el cubo es el digest del `scenario_id`, no un sorteo—, de modo que una puntuación de hoy y otra del mes que viene son comparables y un cambio no puede elegir a qué escenarios le toca juzgarlo. Sobre el corpus real: 55 escenarios, 25 skills, 41 de entrenamiento y 14 de validación al 30 %. **Catorce es poco** para distinguir mejoras pequeñas, y la propia partición lo dice en vez de esconderlo.
- Queda `IMPLEMENTED_NOT_VERIFIED`: ejecutar los escenarios contra un modo DSH real no se ha hecho, así que el gate está probado contra observaciones sintéticas y ningún cambio de biblioteca ha pasado por él todavía.
- Suite: 630 OK (3 saltadas).

## Un lease por fichero para que dos sesiones no se pisen — 2026-09-30
- **Nada del backend de ficheros convierte un reemplazo de cinco ficheros en una transacción**, así que la no atomicidad por lotes se sigue declarando: `write_method: workflow_write-full-replacement-not-atomic` no cambia. Lo que sí se cierra es el fallo más estrecho que esa declaración permitía — dos sesiones reemplazando el mismo fichero a la vez, la segunda descartando una escritura que nunca vio.
- `workflow_write` toma un lease por fichero antes de `writeText` y lo libera después, con TTL de 30 s para que una sesión muerta no deje el estado bloqueado para siempre; un lease vivo de otra sesión deniega la escritura nombrando el titular y su antigüedad, y uno caducado se toma. El preflight ignora `<stateRoot>/.leases` con nota: sin eso, instalar fallaría porque una commences a mitad de escritura, y el nombre empieza por punto, que la regla de seguridad del estado rechaza. Regresión con los cinco casos: lease ajeno vivo deniega, caducado se toma, el titular reentra, la escritura lo deja en `released`, y la raíz de evidencia no toma ninguno porque no es estado. Una sesión sin identidad no toma lease: un candado que todos tienen no es un candado.
- Suite: 625 OK (3 saltadas).

## El hallazgo dice por qué existe y qué lo impediría — 2026-09-30
- **`cause` y `prevention`**, cada una de 1 a 256 bytes: por qué existe el defecto y qué impediría que volviera. Es lo que convierte una lista de hallazgos en trabajo prevenible, y ambas están acotadas porque el registro entero vive en 4.096 B.
- **`evidence.fingerprint` calculado sobre el código citado**, no sobre la redacción. La clave de deduplicación es `(finding_id, base_revision)`, así que una reauditoría que describe la misma línea con otras palabras generaba un segundo registro y la cola crecía con duplicados invisibles; ahora «mismo defecto, otras palabras» comparte fingerprint y se puede contar. Lo calcula la herramienta, que también rechaza que el modo lo escriba.
- **El tope del registro se comprueba en el límite de escritura**, no en el preflight de la siguiente instalación: un registro que excede 4.096 B se rechazaba cuando ya no había nadie quecould corregirlo, y ahora el rechazo dice cuántos bytes ocupa y qué acortar.
- Los tres campos son opcionales: la evidencia de las cuatro campañas sigue activándose sin cambios, con regresión propia para las dos mitades.
- Suite: 623 OK (3 saltadas).

## Distinguir la auditoría completa de la incremental — 2026-09-30
- **La plantilla ordenaba leer el estado antes de auditar**, que es justo lo contrario de lo que necesita una revisión completa: el modelo se ancla a la cola y vuelve a encontrar lo que la cola ya tenía. Una petición que nombra el proyecto entero ahora obliga a formar observaciones propias primero y a contrastar el diagnóstico persistido con ellas; una petición que nombra un flujo, una característica o un componente sigue partiendo del diagnóstico, que es lo correcto para una incremental.
- El alcance se declara en la respuesta y viaja en el `handoff_id` (`audit-complete-<base8>-<n>` frente a `audit-<base8>-<n>`), y `bootstrap.py state` cuenta ambos. Sin eso la distinción era una frase del prompt, y una frase del prompt no se puede auditar a posteriori.
- Suite: 621 OK (3 saltadas).

## La evidencia grande tiene casa propia y topes — 2026-09-30
- **Un parche de 4,0 MB y un log de 5,8 MB acababan archivados como `unexpected-evidence`.** No era un defecto del preflight: un registro de hallazgo vive en 4 KiB y un artefacto grande no cabe, así que la única dirección posible era la raíz del estado — donde el preflight la trata como fichero intruso y la archiva con recibo. Trabajo legítimo tratado como basura por no tener dónde vivir.
- Ahora los parches de candidata, los logs de herramienta y la salida larga de comandos van a `real_stack_verification.artifacts.root`: un hermano de `mode-state` dentro del mismo workspace, con topes propios (8 MiB por fichero, 256 MiB totales, 200 ficheros) comprobados **antes** de escribir y nombre seguro. Lo que se descarte deja recibo en `overflows.jsonl`. Los resultados de verificación nunca van ahí: siguen en `mode-state`, porque son registros que preflight y Host validan.
- La superficie escribible no se ha ampliado: `workflow_write` acepta la raíz de evidencia y sigue negando cualquier otra cosa, incluidos los ficheros sueltos del workspace y el producto. Regresión con los seis casos: artefacto aceptado, nombre con `..`, ruta anidada, fichero suelto del workspace, escritura dentro del producto y artefacto por encima del tope por fichero.
- Suite: 619 OK (3 saltadas).

## El hallazgo ancla su evidencia y la herramienta la localiza — 2026-09-30
- **La evidencia `archivo:línea` era prosa dentro de `summary`, y por tanto nada podía comprobarla.** Un hallazgo podía afirmar una línea que no existía y el estado lo aceptaba, porque el registro no tenía ningún campo verificable. Ahora el hallazgo lleva `evidence.path` y `evidence.excerpt` —un fragmento literal con su propia indentación— y **`line` y `located` los calcula `workflow_write`**: localiza el fragmento en el producto antes del write-intent, usando el `product` que declara el plan de capacidades firmado por digest, y escribe la línea que encontró.
- **Un ancla que no se puede colocar no se coloca nunca.** El fragmento que no aparece en el fichero, o que aparece más de una vez, **rechaza la escritura** nombrando el caso; el modelo cita un fragmento único y reintenta, nunca adivina una línea ni rellena el excerpt para que encaje. Un hallazgo sin localización posible —arquitectura, capacidad ausente— se persiste sin `evidence`, que es honesto y visible en `bootstrap.py state` (`anchors: {anchored, unanchored}`) en vez de un hueco. La técnica viene de `alibaba/open-code-review` (`internal/diff/resolver.go` y `internal/llmloop/loop.go:721`), leído por dentro: declines por ambigüedad y deja el comentario sin localizar *antes* de que el modelo pueda sobrescribir la evidencia.
- **El campo es opcional en el schema, a propósito.** Exigirlo en el preflight archivaría la evidencia de las cuatro campañas, y la evidencia histórica no se migra ni se recalifica. Regresión propia: un registro antiguo de cinco campos sigue siendo válido, uno con ancla bien formada se activa con su línea, y solo uno mal formado (campo extra en `evidence`, `line: 0`) se descarta con recibo que lo nombra.
- **Dos fuentes externas registradas, leídas por dentro y con decisión razonada.** `microsoft/skillopt` (`fa4ca18`, MIT) y `alibaba/open-code-review` (`a758d9c`, Apache-2.0) entran en `library/source-registry.json` como `CANDIDATE`. De skillopt se toma el diseño de RSI —aceptación solo si mejora estrictamente el holdout, buffer de ediciones rechazadas con score antes/después que se realimenta a la reflexión, regiones protegidas que nunca introducen reglas nuevas, abstención declarada cuando el holdout no es disjunto— y **no** el motor: `pip install skillopt` mete una cadena de modelos que la política de distribución no permite. De open-code-review se toma el anclaje y no la dependencia: un informe externo no puede ser evidencia de verificación bajo G7.
- **Corrección de una afirmación previa.** Dije que open-code-review validaba la respuesta del LLM contra JSON Schema; eso venía de su `ASSURANCE_CASE.md` y no existe en el código — las validaciones son de configuración, sesión e informe de reintentos. La entrada del registro lo deja escrito para que no se repita.
- Suite: 618 OK (3 saltadas).

## El recuento de la auditoría y la reconciliación del estado — 2026-09-30
- **`persisted_count` era una afirmación del modo sobre sí mismo.** El contrato lo declara `final_field` y la persona pide reportarlo, pero nada lo contrastaba con `findings.jsonl`: un turno que no persistió nada podía responder con un número, que es exactamente lo que pasó tres turnos seguidos en RehabWeb. Ahora `audit_count_command` (generado centralmente, como los de Repair) recalcula desde el fichero el conjunto de hallazgos `OPEN` en la base declarada, verifica que el handoff lo cubre exactamente e imprime `__IMPROVEMENT_AUDIT_COUNT__`; el número reportado es el impreso. El lifecycle declara `persist_order`, la regla de `persisted_count` y `handoff_coverage`.
- **Un handoff que deja hallazgos fuera de la cola ya no se escribe.** `workflow_write` valida `handoffs.jsonl` contra `findings.jsonl` antes del write-intent: todo id nombrado tiene que existir en esa misma base, y el handoff de auditoría (el que lleva el `next_prompt` exacto del contrato) tiene que nombrar **todos** los `OPEN` de esa base y ninguno más. El caso que lo motivó es de Syncify: seis hallazgos consecutivos con work item y ningún handoff de repair que los cubriera. Un handoff de Repair sigue llevando solo los hallazgos que tomó, porque la cobertura es la afirmación de la auditoría.
- **`PARTIAL` no entra al enum: se deriva.** RehabWeb persistió `PARTIAL` y `REPAIRED` contra el contrato, y el caso real que describen —las pruebas pasan, el lint no puede correr— no tenía nombre. La solución no es ensanchar el enum: cada entrypoint del plan conserva su resultado cerrado (PASS/FAIL/BLOCKED), se escribe un registro por entrypoint ejecutado (la clave de dedupe pasa a incluir `command`) y el veredicto por hallazgo lo deriva el Host con peor resultado ganando (FAIL > BLOCKED > PASS). Un stack con capacidades no se ablanda declarando un estado mixto, y dos registros que dicen PASS y FAIL sobre el mismo árbol se rechazan como contradicción, tanto en `stack.validate_verification_results` como en el plugin. `REPAIRED` no entra: describe el arreglo, no lo que dijo el entrypoint.
- **`scripts/state_reconcile.py` + `bootstrap.py state`.** El estado gestionado describe hechos que viven fuera y pueden contradecirlo en silencio: la cabeza integrada que un `amend` o un `rebase` borró de la rama canónica, los hallazgos que el ledger sigue llamando `OPEN` aunque su work item sea `VERIFIED` (30 de los 42 de Syncify), y los `OPEN` que ningún handoff tomó. El informe nombra los tres sin reescribir el ledger. `--repoint` mueve el registro solo a una revisión que git prueba ancestro del HEAD canónico con producto limpio, y deja recibo en `overflows.jsonl`; `--retire` borra worktree y rama de una `INTEGRATED` solo cuando su cabeza está en la canónica, el worktree registrado es el suyo, coincide con la registrada y está limpio — y es idempotente. Las tres cosas se corrigieron a mano dos veces cada una; ahora son una comprobación.
- **G0 cerrada: Apache-2.0.** `LICENSE` en la raíz con el texto canónico (sha256 `cfc7749b…` del original de apache.org) y la referencia en el README. G6 —tag `v0.1.0-beta` y publicación— sigue sin hacer: requiere autorización de destino.
- **Documentación alineada con lo que el código ya hacía.** `PLAN_IMPLEMENTACION.md` cerraba P10 y P11 como `EN CURSO` mientras el estado y el CHANGELOG dan las campañas por cerradas; se cierran y se añade la sección «Deuda declarada» (D1–D12) para que ninguna deuda viva se lea como `HECHO`. `docs/audit-contract.md` decía que `decisions.py` y `metrics.py` no se exigían ni se enlazaban: es cierto de `audit.py` y falso del ciclo, que los escribe al cerrar turno desde `host_controller.py` desde G2. `docs/external-orchestration-draft.md` pasa de borrador sin estado a material de diseño de D11, retomado por decisión del titular y con su condición de decisión sin medir.
- Suite: 615 OK (3 saltadas).

## La evidencia atada al árbol que verificó — 2026-09-30
- **IMP-AUD-008 (HIGH), encontrado re-auditando el framework con sus propios modos.** Un resultado de verificación nombra un hallazgo y una `candidate_head`, y nada comparaba esa cabeza con nada. El contrato prohíbe hacer commit de una candidata, así que el árbol verificado es normalmente un worktree DIRTY cuyo HEAD sigue siendo su base y el arreglo vive en el diff sin commitear: `candidate_head` no lo distingue de la revisión anterior al arreglo. Medido sobre el estado vivo del self-test, los siete registros llevaban dos cabezas —`d0f2444` para IMP-AUD-001/002 y `551f145` para el resto— y **ambas anteriores a los cambios que decían verificar**: `git show d0f2444:scripts/dsh-plugins/workflow-write.mjs` filtrando `assertStateWrite` no devuelve nada, y `git show 551f145:scripts/host_validator.py` filtrando `Reference cycle detected` tampoco. W-01 a W-07 figuraban VERIFIED sobre evidencia que nadie podía comprobar.
- El registro lleva ahora `candidate_diff_digest`, la única huella del árbol reparado, y tres sitios lo exigen: el preflight descarta un registro cuyo digest no es el registrado en `work-items.json` y deja recibo nombrándolo —con lo que `stack.validate_verification_results` deja de ser código solo de test y tiene un llamador de producción—, el plugin exige el campo y su forma en el momento de escribir, y la persona ordena copiar verbatim el digest registrado y dice qué significa un desajuste. Contrato nuevo: `real_stack_verification.verification_identity: candidate-diff-digest-must-match-work-items`.
- **LoboApp llega al final.** Los 9 hallazgos de la primera auditoría se repararon e integraron en cuatro turnos, la reauditoría los confirmó como `RESOLVED` con evidencia y encontró 5 más —uno creado por el arreglo anterior, que al comparar espacios de nombres dejó sin poder restaurar un respaldo heredado sin namespace—. Total 14 hallazgos cerrados, `bb01cba..4c0bb30`, 166 pruebas Flutter en verde y `flutter analyze` sin incidencias. El marco aguantó un entorno donde DSH se cae cada varios minutos: producto intacto hasta la integración, candidatas registradas y reconciliadas, base declarada re-anclada al HEAD con la ascendencia comprobada por `git merge-base --is-ancestor` dentro del comando de provisión.
- Suite: 606 OK (3 saltadas).

## El framework auditándose a sí mismo — 2026-09-30
- **El self-test encontró dos defectos reales, no triviales.** Instalado de cero sobre un clon de sí mismo (`install` con el entrypoint declarado `python3 -B -m unittest discover -s tests`), el auditor persistió 7 hallazgos (2 HIGH, 5 MEDIUM) con evidencia y handoff: `Creator: GENERATED` (18 artefactos) → `Host: ACTIVE` con `published_presets: [improvement-auditor, improvement-continuous-repair]`, preflight sin descartes, y plan con `python-unittest: listo`. Los siete acabaron reparados e integrados; la reauditoría posterior los confirmó como `RESOLVED`.
- **IMP-AUD-001 (HIGH) · la compactación por límite perdía registros sin recibo.** El trabajo de G3 cubría el descarte por incompatibilidad de esquema, pero `_jsonl` e `initialize_state` quitaban en silencio lo que excedía el tope: un archivo que crecía por encima de su cap perdía entradas que nadie podía nombrar después. El descarte por límite toma ahora la misma ruta —recibo en `overflows.jsonl` y copia archivada— tanto en la proyección JSONL como en los work items. Regresión en `tests/test_mode_lifecycle.py`.
- **IMP-AUD-002 (HIGH) · la escritura de estado no estaba confinada.** `validateManagedVerification` acotaba solo `verification-results.jsonl`; el resto del estado gestionado se escribía donde el modelo pidiera, con la frontera de solo lectura del auditor apoyada únicamente en el Git posterior. Una sesión gestionada declara ahora su raíz `<workspace>/mode-state` —derivada de la sesión, no del destino, porque anclar en el destino solo prueba que la ruta *parece* estado— y todo destino fuera de ella se deniega antes del write-intent, incluida una ruta con `..` que `processPath` conserva en vez de normalizar. Una sesión sin workspace gestionado conserva el comportamiento anterior, que es lo que necesita el revisor de aceptación. Regresión en `tests/test_workflow_write_plugin.py`.
- **La evidencia de la beta sobre el framework es su propia suite real:** `/usr/sbin/python3 -B -m unittest discover -s tests`, 606 pruebas en verde, registrada en `verification-results.jsonl` con el schema estricto y el comando exacto del plan. El producto (`clon de Improvement`) quedó intacto hasta la integración, y el operador integró con commit y fast-forward.
- Detalle operativo: DSH se cae cada varios minutos en este entorno y se relanza como unidad de usuario de systemd con `Restart=always`; `--no-open` solo se acepta después del path del overlay.

## G7 · Beta sobre stack real: el entrypoint tiene que existir de verdad — 2026-09-29
- **Un `flutter test` desnudo nunca iba a correr.** El plan detectaba el SDK por su ruta absoluta y aun así emitía el comando `["flutter","test"]`, que la shell del modo no resuelve porque el SDK vive en `~/.local/share/flutter`. El registro de verificación debe repetir el comando exacto del plan y el plugin rechaza cualquier otro, así que una suite perfectamente capaz se habría registrado como `BLOCKED` por un nombre, no por una carencia real. El plan nombra ahora la capacidad por la ruta con la que se puede invocar, y deja el nombre suelto solo cuando el PATH por defecto ya lo resuelve (el caso común sigue leyéndose como la documentación del producto).
- **`workspace-write` deja montado en solo lectura tu SDK, y Flutter se reescribe en cada invocación.** `bin/internal/update_engine_version.sh` sella la versión de engine en `bin/cache/engine.stamp` de forma incondicional en cada ejecución, así que calentar la caché no ayuda: el sandbox no admite la escritura y el turno muere con `Read-only file system`. Separar "esta capacidad puede correr" de "esta sesión puede escribir en ella": una capacidad que el PATH por defecto no resuelve es un toolchain que el titular gestiona por su cuenta, y el plan pide materializarla bajo `<workspace>/.stack/<stack>/` y nombra esa copia como entrypoint desde el principio — el registro nombra el mismo comando haya materializado la capacidad primero o haya dado con `BLOCKED`. La copia va con `cp -al`: medido en la campaña real, 17.659 ficheros y 0 bytes de disco, porque la herramienta sustituye por rename y eso rompe el enlace sin tocar la instalación original. La persona de Repair y `real_stack_verification.sandbox_readonly_sdk` describen el paso; la resolución del plan sigue siendo datos y no ejecuta nada.
- **Campaña de LoboApp (G4) sobre clon de GitHub,** con el framework instalado de cero sobre un producto Flutter recién clonado: `Creator: GENERATED` → `Host: ACTIVE` con `published_presets: [loboapp-auditor, loboapp-continuous-repair]` y plan con `dart-flutter` listo más `java-gradle` sin JDK. El prompt simple de auditoría persistió 9 hallazgos (1 CRITICAL, 2 HIGH, 4 MEDIUM, 2 LOW) con evidencia `archivo:línea` y su handoff con los 9 IDs, los 9 work-items derivados y el producto intacto en `bb01cba`. El primer Repair aprovisionó la candidata determinista y persistió el registro de candidata **literalmente** (`verbatim_identical: True`, mismo orden de campos), comprobando en vivo el contrato de G1.
- **Dos fallos los atrapa la maquinaria, no la confianza.** Una sesión creada con el cwd equivocado se retiene de inmediato en lugar de auditar un árbol que no le tocaba (sentinel de layout). Y DSH muere con su proceso padre: el servidor estable se lanza como unidad de usuario de systemd, con `--no-open` colocado después del path del overlay (`dsh web --patch <file> --no-open`), que es la única posición donde el parser lo acepta.
- Suite: 582 OK (3 saltadas).

## G7 · Verificación contra el stack real, sin stubs — 2026-09-29

- En rehab el Repair verificó con un arnés de stubs porque el stack real (Django) no estaba instalado, y ese arnés no demuestra el comportamiento del producto: era el contrato lo que lo permitía. Nuevo módulo `scripts/stack.py` (plan de capacidades, ligado a digest, fail-closed) que detecta el stack del producto por lockfile/manifiesto —incluidos subdirectorios de monorepos como `backend/` y `frontend/`— y para proyectos sin manifiesto acepta la declaración explícita del titular (`improvement-verification.json`). El plan nombra el entrypoint propio del producto (tests y lint con su cwd), el estado real de cada capacidad del runtime y el paso exacto de provisión para cada una ausente, siempre fuera del producto salvo rutas que el propio producto ignore (marca `in_product_install_gitignored`); una clon de Flutter sin su cache de engine no cuenta como capacidad.
- Contrato (`real_stack_verification` en el lifecycle de ambos modos + persona y prompt de Creator): la evidencia de verificación es el entrypoint propio del producto o `BLOCKED` nombrando la capacidad y su paso; un arnés, mock o copia del código escrita a mano es material de investigación y jamás un resultado; para instalar capacidades se sigue el `provision_step` del plan, nunca dentro del producto fuera de rutas ignoradas. La validación mecánica `validate_verification_results` y el límite de escritura `workflow_write` rechazan cualquier registro que no cumpla exactamente el schema estricto de `verification-results.jsonl` (`finding_id`, `candidate_head`, `result`, `command`, sin campos extra), cualquier `command` que no sea uno de los entrypoints exactos ligados al plan y PASS/FAIL cuando la capacidad está ausente; la transacción escribe el plan al instalar y lo publica en el resultado (`capability_plan`), y `bootstrap.py stack --project … [--write] [--json]` lo resuelve bajo demanda. Verificado con los repos reales y sus stacks ya materializados: RehabWeb, 84 pruebas Django reales OK; LoboApp, 119 pruebas Flutter reales OK y `flutter analyze` sin incidencias; ambos árboles quedaron limpios. El plan también detecta Node en el `frontend/` de RehabWeb (con `node_modules` NO ignorado), Gradle en `android/` (sin JDK) e Improvement sin manifiesto. Suite: 579 OK (3 saltadas).

## Re-anclaje de base declarada — 2026-09-29

- Cuarto turno de Repair sin persistir sobre RehabWeb finalmente diagnosticado con la transcripción real: no era la desviación de campos de G1. El modo se detuvo **correctamente**: los hallazgos declaran base `5e638f0`, el `provision_command` exige que el HEAD del producto coincida con la base declarada, y tras integrar la candidata anterior (`c5141bd`) el producto había avanzado — historia divergente, `RETAINED` duro. El defecto era del contrato: sin ruta de re-anclaje, integrar una candidata bloqueaba todo ciclo de reparación posterior sobre los mismos hallazgos (los cuatro turnos fallidos comparten esta causa).
- El contrato de Repair incorpora `stale_base_policy: re-anchor-when-declared-base-is-ancestor-of-clean-head`: si la base declarada difiere del HEAD canónico, el modo prueba `git -C <product> merge-base --is-ancestor <declared-base> HEAD` y exige producto limpio; solo con ancestro probado y producto limpio reancla (base efectiva = HEAD canónico actual, identidad derivada de ella, `base_revision` de la candidata = base efectiva, ambas bases declaradas en el informe final). Hallazgos y handoffs conservan su base declarada como procedencia. Cualquier otra relación (historia divergente, reescrita o forzada, producto sucio, base desconocida) sigue siendo `RETAINED` duro. Persona, prompt de Creator y arquitectura actualizados; regresión con el caso real (ancestro + HEAD limpio: la base efectiva aprovisiona y la declarada falla cerrado). Suite: 566 OK (3 saltadas).

## G1–G3 del plan de lanzamiento — 2026-09-29

- **G1 · Contrato de candidata.** Causa raíz del patrón RehabWeb (tres turnos de Repair sin persistir nada; candidatas con campos extra y `path` absoluto) encontrada y eliminada: el `recording_command` imprimía una línea de 5 campos con ruta absoluta que el esquema del candidato rechaza, así que ningún modo podía persistirla verbatim y la traducción manual era la desviación. Ahora el `recording_command` y el `reconcile_command` emiten tras su marcador el objeto JSON exacto a persistir (ruta relativa del candidato, head en base, estado y evidencia de diff ya incluidos), la persona prohíbe añadir, quitar, renombrar, reordenar o alterar campos y ordena `RETAINED` si el objeto verbatim no se puede persistir, y el prompt de Creator fija la misma regla para las generaciones. El preflight (`initialize_state`) devuelve un informe que nombra cada archivo reemplazado y los registros descartados —incluidos ítems y candidata inválidos de `work-items.json`, no solo los jsonl— y la transacción de instalación lo incluye en su resultado (`mode_state_preflight`) para que el operador lo vea, no solo el archivo legacy. Regresión RehabWeb: el objeto emitido valida contra el esquema del candidato en `PROVISIONED` y `DIRTY`, y los campos extra o la ruta absoluta quedan fuera por construcción.
- **G2 · decisions + metrics al ciclo.** `decisions.py` y `metrics.py` dejan de ser huérfanos: el controlador Host abre ambos almacenes por misión (`metrics/`, `decisions/`) al registrar o reabrir el mandato y los llama en cada cierre de turno —evento `turn` con `elapsed_s` cuando está observado en `UNIT_DONE` y `UNIT_RETAINED` (también en `cancel`)— y en toda retención registra la decisión ratificada por el Host (causa como motivo, unidad afectada, autorización del mandato). Fail-closed: una escritura fallida deja la unidad en vuelo para reconciliación en vez de fingir un cierre limpio; reabrir una misión con identidad de almacén alterada falla.
- **G3 · Compactación con recibo.** El estado activo gana `overflows.jsonl` (límite 100, dedupe `overflow_id`, esquema con `file`/`reason`/`dropped_records` ≤32): el contrato del ciclo exige que antes de cualquier reemplazo que descarte registros por límite o deduplicación el modo persista primero el recibo, de modo que la compactación de runtime (caso Syncify: 50/50 handoffs) nunca pierde registros sin traza. El preflight migra y valida el archivo nuevo como los demás y las regeneraciones lo incorporan al lifecycle.
- Arquitectura actualizada en los tres puntos (emisión verbatim, informe de preflight, recibo de desbordamiento y memoria de misión del Host); plan de lanzamiento marca G1–G3 HECHO; `docs/status.md` refleja el avance. Suite: 565 pruebas OK (3 saltadas), incluidas 9 regresiones nuevas.

## Preparación de lanzamiento público beta — 2026-09-29

- Plan de puertas G0–G6 en `docs/plans/10-lanzamiento-publico.md`: licencia (G0, decisión del titular), endurecimiento del registro de candidata ya declarado (G1), cablear `decisions.py`/`metrics.py` al cierre de turno (G2), compactación de runtime con recibo de desbordamiento (G3), E2E desde clon de GitHub sobre repo demo (G4), documentación pública (G5) y tag `v0.1.0-beta` con notas (G6). La línea base medible del piloto queda en el plan para comparar durante la beta.
- README reescrito como página pública: qué es, cómo funciona, requisitos, comando único de instalación, uso con prompts reales, dos casos de uso con métricas verificables del piloto (Syncify: 77 hallazgos distintos, 78 items VERIFIED, 67 verificaciones, 15 commits de los modos, CI verde en 3 jobs; RehabWeb: 45 hallazgos con 6 CRITICAL, 2 reparados con un prompt de seis palabras), límites honestos y estado beta.
- `docs/status.md` añade la fila de preparación de lanzamiento y la meta vigente; el informe del mantenedor (fuera del árbol) se completa con los incidentes en vivo de la campaña que la arqueología de ficheros no podía ver: disco lleno por candidatas integradas sin retirar (321 GB, dos turnos perdidos y reanudados por el reclamo `PROVISIONED`), dos fallos de CI por capacidad del runner (FFmpeg 6.1.1), el deadlock de `batch_50` diagnosticado observando 0 % CPU y `futex_wait`, la autoría de commits de integración corregida con force-with-lease, y las dos verificaciones que la investigación dejó pendientes y el operador ejecutó en vivo (roster de fábrica confirmado; suite 556 OK).

## Instalación limpia sobre RehabWeb y forma del registro de candidata — 2026-09-29

- La instalación de principio a fin se ejecutó sobre un entorno sin contamination: clon nuevo de Improvement, clon nuevo de RehabWeb y un home de DSH nuevo con solo credenciales y modelos, cuyo roster inicial tenía únicamente los cuatro presets de fábrica. Un único `bootstrap.py install --project … --launch-dsh` produjo `Creator: GENERATED` (20 artefactos) y `Host: ACTIVE` con `published_presets: [rehabweb-auditor, rehabweb-continuous-repair]`. Un prompt simple («Audita completamente este proyecto; no modifiques ni publiques.») persistió 45 hallazgos —6 CRITICAL, 16 HIGH, 23 MEDIUM— con evidencia `archivo:línea` y su handoff; otro prompt de seis palabras («Repara A-SEC-01 y A-SEC-02; no publiques.») aprovisionó la candidata determinista, la reclamó `PROVISIONED` antes de editar, reprodujo ambos defectos contra la revisión base con un harness de stubs, aplicó el arreglo, añadió la prueba de regresión y dejó el árbol del producto intacto. El operador integró con commit, fast-forward y push.
- El piloto encontró además un fallo de contrato: el modo Repair generado por esa ejecución persistió `work-items.json.candidate` con una forma propia —`path` absoluto, `base` en vez de `base_revision`, campos extra `finding_ids` y `record_line`— que el validador del framework rechaza. El contrato generado sí era correcto (`recording_command` presente, `record_before_first_edit: true`), así que la desviación está en la traducción del modo, no en el contrato: el comando central imprime una línea de shell y el modo decide el JSON. Reintentado con un prompt explícito, el modo mantuvo su forma. Consecuencia práctica: el preflight archivarían el `work-items.json` completo y pondría `candidate` a null en el siguiente ciclo, en silencio. Registrado como próxima unidad de endurecimiento: que el comando central emita el objeto JSON exacto que hay que persistir y que la persona prohíba añadir campos, más un surfacing en el informe de preflight de lo que se descarta. En esta instalación el Host normalizó el registro con su propio validador y lo dejó `INTEGRATED`.

## Reclamo y reconciliación verificados en DSH real — 2026-09-29

- El ciclo auditor→reparador→integración completó una vuelta completa sobre Syncify con los contratos nuevos y sin intervención técnica del operador. Una auditoría con prompt simple persistió seis hallazgos (`SYNC-AUD-054`…`059`) y su handoff contra `9afdc0f`; el turno de Repair ejecutó el `recording_command` central y persistió la candidata como `PROVISIONED` **antes** de cambiar ningún byte, la re-registró `DIRTY` tras el primer cambio con digest y paths, y —tras un segundo prompt que amplió la reparación a once archivos— volvió a persistirla con un `candidate_diff_digest` nuevo y la lista completa de `changed_paths` coincidente con el diff real. Ninguna colisión, ningún `RETAINED`, ninguna decisión del operador: el camino `PROVISIONED → DIRTY → re-registro` que motivó `record_before_first_edit` funcionó tal cual está especificado, y el operador integró solo con commit, fusión fast-forward y push, que es exactamente la frontera que el contrato le asigna. El verificador Host y la suite local (553 pruebas) siguen en verde. Quedan como límites declarados, no como defectos: la actualización multiarchivo no tiene CAS/lease y bash conserva alcance de escritura del padre común, así que no se afirma aislamiento ni atomicidad concurrente.

## Digest de diff obsoleto se reconcilia sin operador — 2026-09-28

- Tras añadir el reclamo, un turno real de Repair encontró su candidata registrada pero con `candidate_diff_digest` obsoleto: el turno anterior había registrado un digest y siguió editando antes de terminar. El contrato lo trato como colisión dura y el turno pidió decisión del operador para reemitir el registro o descartar la candidata, un callejón sin salida para un usuario no técnico que solo puede enviar prompts simples. El lifecycle incorpora `stale_record_policy: reconcile-then-resume` y un comando central de reconciliación que recalcula el digest de hallazgos y su `digest16` desde la revisión base más los IDs reales —nunca confiando en la identidad declarada por el llamador— y solo re-mide el diff actual cuando identidad target, worktree registrado, HEAD base, canonical limpio e inalterado, diff no vacío, paths confinados sin symlinks y ausencia de submódulos ya comprobaron que esa candidata es de Improvement. Cualquier discrepancia real de path, branch, base o digest de hallazgos sigue siendo `RETAINED` duro, y un target sucio sin registro nunca se adopta. Persona, prompt de Creator, schema, arquitectura y estado fijan el contrato. Regresiones reproducen el caso real: digest obsoleto que reconcilia y reanuda conservando los bytes candidatos, y rechazo fail-closed ante hallazgos ajenos, otra candidata y base obsoleta. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir prueba DSH real.

## Reclamo de candidata antes de editar — 2026-09-28

- Un turno real de Continuous Repair aprovisionó su candidata determinista y la editó, pero terminó sin persistir `work-items.json.candidate`. El turno siguiente encontró ese worktree sucio sin registro y, correctamente según el contrato anterior, quedó `RETAINED` sin poder repararlo nunca: la reanudación estricta solo acepta un target ya registrado. El bloqueo de seguridad era correcto; lo que faltaba era el paso que hace imposible quedar en ese estado. El lifecycle incorpora ahora `record_before_first_edit: true`, `record_statuses: [PROVISIONED, DIRTY]`, un `recording_command` central y `unrecorded_dirty_target: RETAINED-never-adopted`. Repair debe ejecutar ese comando justo después de provisionar y persistir la candidata como `PROVISIONED` antes de cualquier llamada que cambie código; si el reclamo no se puede persistir no edita y queda `RETAINED`. Tras el primer cambio repite el comando y persiste `DIRTY` con digest y lista de paths, de modo que una candidata registrada que ya aparezca sucia es un turno interrumpido y se recupera con el mismo comando (`interrupted_turn_recovery`), nunca creando otra ni descartando su diff. Un target sucio sin registro sigue sin adoptarse jamás. La política de reanudación pasa a `resume_policy: exact-recorded-only` porque la reanudación cubre ahora el registro `PROVISIONED` además de `DIRTY` y `RETAINED`; `PROVISIONED` no exige evidencia de diff en el schema, que sigue exigiéndola para `DIRTY` y `RETAINED`. Persona, prompt de Creator, schema, plantilla, arquitectura y estado fijan el contrato. Regresiones ejecutan el comando real contra repos temporales: reclamo limpio, recuperación del turno interrumpido con bytes intactos, y rechazo fail-closed ante target ausente, base obsoleta o target no registrado. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir prueba DSH real.

## Resolución viva del guard anti-escalada — 2026-09-27

- El preset generado era inválido en el runtime DSH vigente: el registro recibe `config.plugins` embebido en `cordis.patch.yml`, por lo que `./anti-escalation.mjs` se resolvía desde el patch instalado y la fila nunca arrancaba. La fuente generada y su validación conservan la identidad scoped exacta `./anti-escalation.mjs`, pero la publicación materializa esa única fila con la ruta absoluta del guard copiado al mismo bundle y `agentPresets/read` comprueba la identidad efectiva. La regresión de runtime usa el `@deepseek-ai/dsh-agent-preset` y el boot API vigentes, monta las siete filas exactas publicadas y demuestra bash ordinario junto al bloqueo pre-aprobación de `workspace-write` y `danger-full-access`.

## Anti-escalada mecánica en modos finales generados — 2026-09-27

- Un Continuous Repair generado envió `sandbox_permissions: require_escalated`, reintentó con `danger-full-access` tras el error de schema y quedó esperando aprobación. La prohibición existía para Creator y en el overlay global, pero no formaba parte del lifecycle/persona exactos del modo final ni de su composición scoped. Ambos roles declaran ahora `escalation_channel: forbidden`, los dos argumentos prohibidos para cualquier valor y `denial_policy: RETAINED-no-retry-on-denial-or-schema-error`; la persona first-party repite el contrato y Host/transacción comparan su forma exacta. Cada preset exige `./anti-escalation.mjs`, copiado dentro del bundle operacional y comprobado por `agentPresets/read`; el guard rechaza `workspace-write` y `danger-full-access` antes de dispatch/aprobación, mientras bash ordinario sigue funcionando. El overlay global deja de permitir escaladas estrictamente mayores residuales y conserva el saneado de schemas. Regresiones Python, unidad Node y fixture Node contra runtime DSH cubren composición, schema/persona, bash normal y ambos valores bloqueados sin guía de reintento. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta retry DSH vivo.

## Reanudación segura de candidata Repair sucia — 2026-09-27

- Una segunda invocación de Repair no podía reanudar la candidata determinista que el primer turno había modificado y registrado porque la reutilización exigía limpieza. El lifecycle incorpora `resume_policy: exact-recorded-dirty-only`, lectura previa del `candidate` estricto de `work-items.json` y comandos centrales separados para capturar digest/lista de paths y validar reanudación. Solo permite `DIRTY` o `RETAINED` pendiente de verificación con coincidencia exacta de path, branch, base y digest de hallazgos; recomprueba identidad worktree, HEAD base, canonical limpio e inalterado, diff no vacío byte-idéntico, paths completos confinados a archivos regulares sin symlinks y ausencia de submódulos, sin exigir candidata limpia ni cambiar bytes. Registro ausente o discrepancias de digest/path/base/status mantienen la colisión `RETAINED`; nunca se adopta un worktree sucio arbitrario. Persona, schema, arquitectura y estado fijan el contrato. Regresiones ejecutan dos turnos reales y los rechazos, preservando bytes candidatos e invariancia canónica. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir prueba DSH real.

## Preflight Repair limitado a la identidad target — 2026-09-27

- Un Repair real inspeccionó una candidata gestionada anterior ajena y exigió que estuviera current/dirty, bloqueando la provisión aunque el nuevo path y branch deterministas no existían. El `provision_command` central comprueba ahora solo invariantes canónicos y la identidad target; puede leer la lista completa de worktrees únicamente para comparar ese path y branch. Cualquier candidata ajena se ignora y preserva aunque esté clean, dirty, stale/prunable o en otra base (`unrelated_candidates: ignore-preserve`), y la reutilización solo acepta path+branch target del mismo worktree con HEAD base y árbol limpio. Persona, prompt, schema, arquitectura y estado fijan la frontera. Regresiones prueban creación con múltiples worktrees ajenos clean/dirty/stale sin cambiar sus refs, bytes ni registros, reutilización exacta del target y colisiones target fail-closed.

## Provisión Repair como worktree hermano desde cwd de sesión — 2026-09-27

- Una ejecución DSH real partió del padre común, pero combinó `git -C ./<producto>` con un destino relativo y después usó `.` como workdir de cambios; Git resolvió la candidata bajo el producto canónico y lo dejó untracked-dirty. El lifecycle genera ahora centralmente un `provision_command` exacto que se ejecuta con workdir omitido desde el cwd de sesión, calcula `candidate="$PWD/<candidate-name>"`, crea el worktree con destino absoluto y verifica realpath, toplevel y registro. El contrato fija `candidate_root: ${session-cwd}/<candidate-name>`, prohíbe nesting bajo producto y exige para bash posteriores el `candidate_workdir` relativo exacto, nunca `.`. Persona, prompt, schema y validador comparten la forma; regresiones ejecutan el comando en repos temporales, comprueban sibling, canonical limpio, branch/HEAD/registro y rechazan colisiones de path y branch. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir la prueba DSH real.

## Workdir inmutable durante todo el turno Auditor — 2026-09-27

- Una auditoría DSH real superó correctamente el startup con sentinel, pero una llamada bash posterior fijó `workdir: Syncify/ui`; el reintento con `npm --prefix` no reparó el drift ya observado y el resultado quedó correctamente `RETAINED`. El lifecycle declara ahora para Auditor `bash_workdir: session-cwd-only-all-calls`: toda bash omite workdir o usa exactamente `.`, y cualquier comando planeado para otro directorio se reescribe **antes** de invocarlo mediante `git -C`, `npm --prefix`, `cargo --manifest-path` o equivalente; `cd` y workdirs de subdirectorio están prohibidos, y cualquier override accidental retiene inmediatamente sin reintento. Persona, prompt, schema/contratos, arquitectura y regresiones fijan la regla; Continuous Repair conserva el permiso distinto de usar el workdir candidato exacto para comandos que cambian código. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir la prueba DSH real.

## Startup exitoso reconocido por sentinel DSH — 2026-09-27

- DSH devuelve stdout en bash y solo añade `[exit code: N]` cuando `N` es distinto de cero; exigir una marca explícita de exit code retenía falsamente una validación exitosa. El `first_bash_command` exacto conserva `set -eu`, `pwd` y el único `test` de layout, y añade `printf '__IMPROVEMENT_LAYOUT_OK__\n'` únicamente después de que todos pasen. El contrato estructurado incorpora `success_sentinel`; lifecycle, persona y prompt solo permiten continuar si el resultado contiene ese valor exacto, retienen si falta o no hay resultado y prohíben exigir una marca de exit code 0. Regresiones ejecutan el comando real: éxito contiene el sentinel y cada fallo carece de él. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir la prueba DSH real.

## Startup fail-closed con comando Host exacto — 2026-09-27

- El comando inicial generado centralmente comienza por `set -eu`, imprime `pwd` y reúne basename/product root/workspace root en un único `test`, evitando que un shell continúe después de una comprobación fallida. Lifecycle y prompt incorporan literalmente el mismo `first_bash_command`; la persona debe inspeccionar su exit code y ante fallo o resultado ausente terminar `RETAINED` sin separar, reescribir ni continuar. El cwd esperado se confirma como basename del padre común real de producto y workspace. La inicialización conserva además candidatas válidas con estado `INTEGRATED`; Auditor no las borra y solo Host/operador puede registrar ese estado. Regresiones ejecutan el comando con un root ausente/presente, fijan su texto exacto y preservan la candidata integrada. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir la prueba DSH real.

## Startup de modos ligado exclusivamente al cwd de sesión — 2026-09-27

- Fallo de auditoría final real: el Auditor recibió como cwd el padre común correcto, pero sobreescribió el workdir de su bash inicial con el padre superior y reportó falsamente ausente el workspace. El contrato generado exige ahora que, tras cargar el skill homónimo, la primera bash omita `workdir` o use `.`, ejecute `pwd` y valide los roots exactos `./<PRODUCT_ROOT>` y `./<WORKSPACE_ROOT>`; prohíbe inferir, ascender, buscar o cambiar cwd antes del layout, resuelve después todas las rutas relativas desde el cwd observado e inalterado y deja cualquier drift en `RETAINED`. `mode-layout` conserva el basename esperado del padre derivado al generar sin incrustar la ruta absoluta del mantenedor; lifecycle y persona fijan `startup_workdir: session-cwd-only` y `workdir_override: forbidden-before-layout`. Schema, Host/transacción y regresiones rechazan lifecycle/persona incompletos y comprueban el prompt preciso. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` hasta repetir la prueba DSH real.

## Migración segura de archivos esperados legacy — 2026-09-27

- El preflight ya no pierde ni bloquea evidencia DSH antigua dentro de nombres estrictos: archiva junto con la evidencia inesperada el archivo esperado original completo, con source path, motivo y SHA-256, y activa solo registros schema-valid o el mapeo inequívoco `findings.id` → `finding_id`; formas anidadas red/green, resúmenes sin identidad y work-items incompatibles se conservan sin inventar datos. Descriptores legacy equivalentes se normalizan conservando bytes. Escritura, retirada y rollback siguen siendo transaccionales e idempotentes bajo los caps existentes. Regresiones cubren mezcla válida/incompatible, JSONL completo, work-items list/dict, descriptor y fallo tras retirada. Lifecycle permanece `EN CURSO/IMPLEMENTED_NOT_VERIFIED`.

## Caps de archivo ajustados a evidencia DSH real — 2026-09-27

- Un reintento real produjo `candidate-repair.patch` de 4.005.660 bytes y `m02-fmt-red.txt` de 5.776.531 bytes, por encima del cap inicial. La migración preserva ahora evidencia legacy regular hasta 8 MiB por archivo y 32 MiB totales: suficiente para el caso observado, todavía acotado y sin incorporar esos artefactos al estado activo. Regresiones de frontera aceptan exactamente ambos caps y rechazan un byte por encima.

## Migración conservadora de evidencia legacy de mode-state — 2026-09-27

- La finalización Host archiva entradas legacy inesperadas antes de inicializar el `mode-state` estricto: preflight de nombre/tipo/symlink/hardlink y caps de 2 MiB por archivo/8 MiB totales; copia byte a byte en `.dsh-managed/mode-state-legacy/<digest>/` con inventario y recibo verificados; retirada posterior con rollback de originales y reintento idempotente que reutiliza el archivo sano. La evidencia queda fuera de la memoria activa pero localizable por recibo. Regresiones cubren éxito, bytes, recibo, reintento, rechazos y fallo inyectado sin pérdida. Lifecycle continúa `EN CURSO/IMPLEMENTED_NOT_VERIFIED` a falta de prueba DSH real.

## Hardening adversarial previo al siguiente piloto — 2026-09-27

- El lifecycle generado pasa a `EN CURSO/IMPLEMENTED_NOT_VERIFIED`: persona con bootstrap exacto del skill homónimo, policy de tools por rol, invariantes HEAD/status canónicas y diff candidato, provisioning determinista con digest de full base+IDs y checks cerrados, y eliminación de autorización implícita de commit (`candidate_commit` nullable; árbol sucio o patch). Host/transacción comparten validación de lifecycle/persona y el schema público exige lifecycle por rol. `mode-state` añade schemas de registros, ejemplos, caps de archivo/registro, preflight integral de entradas/symlinks/hardlinks/JSON antes de escribir y migración/compactación acotada. No se afirma aislamiento de bash, atomicidad multiarchivo ni seguridad concurrente: CAS/lease/tool Host dedicado y prueba DSH real siguen pendientes. Regresiones cubren bootstrap divergente, schema público, malformed/oversized/legacy y CLI con `/usr/bin/python3`.

## Handoff durable y candidato automático — 2026-09-27

- Hallazgo del piloto Syncify: Auditor entregó un informe final excelente sin persistir findings/handoff y Continuous Repair rechazó `Repara A-01 y M-02` porque no existían candidato ni memoria durable; el operador tuvo que crear worktree y sembrar JSON manualmente, violando la frontera de que solo los modos instalados modifican productos externos. Creator exige ahora un bloque `mode-lifecycle` JSON exacto por rol en `mode.json` y `SKILL.md`: Auditor lee/compacta/deduplica por finding+base y reemplaza estado completo con `workflow_write` antes de responder; Repair interpreta prompts simples como autorización de crear/reusar un worktree sibling determinista, valida checkout limpio/base, registra identidad, modifica/prueba/commitea solo candidato y nunca escribe canónico, mergea, hace push o publica. Host/transacción fallan cerrado, inicializan schema v1 y archivos acotados sin siembra manual. El camino idempotente devuelve ambos `published_presets`, corrigiendo la única rama real capaz de mostrar cardinalidad menor que el recibo aun cuando la instalación seguía íntegra. Regresiones cubren compacción, inicialización/migración, lifecycle ausente/equivocado, defensa transaccional, límites, prohibiciones/final handoff y cardinalidad de reanudación.

## Identidad exacta de layout en modos generados — 2026-09-27

- Hallazgo del piloto Syncify: Creator sintetizaba `syncify-workspace/mode-state` desde el ID normalizado aunque el sibling real era `Syncify-workspace`; Linux cargaba tools correctamente, pero el auditor terminaba `RETAINED` al no encontrar el estado. El prompt toma ahora los paths autoritativos de `bootstrap-request.json`, exige en ambos modos una identidad estructurada y case-sensitive de producto/workspace/mode-state, y la prevalidación recibe el run. Host y transacción contrastan exactamente esa identidad con el contexto antes de aceptar o instalar; el descriptor existente de `mode-state/project.json` conserva los mismos nombres efectivos. Regresiones cubren layout mixto `Syncify`/`Syncify-workspace` y rechazo de casing incorrecto.

## Configuración obligatoria de fs-search — 2026-09-27

- Hallazgo en DSH real: un preset con `@deepseek-ai/dsh-tool-fs-search` sin `config.sampleOverCapGlobResults: false` es inválido. El prompt Creator y el contrato compartido exigen ahora exactamente ese valor; fixtures y publicación lo preservan. Regresiones cubren configuración ausente y valor incorrecto.

## Actualización de bundle estable fail-closed — 2026-09-27

- Hallazgo en vivo tras instalar `gen-2c08df3a24cb`: `pluginManager/installBundle` persiste el nuevo enlace pero devuelve `application: restart-required` cuando el nombre del bundle ya estaba instalado; la transacción ignoraba ese campo y los IDs todavía presentes en `agentPresets/list` pertenecían a la composición anterior, por lo que movía el puntero y el run a `ACTIVE` falsamente. La publicación exige ahora `applied` en instalaciones frescas y verifica por `agentPresets/read` las seis filas operativas y la raíz de skills exacta del candidato. `restart-required` no hace rollback deshonesto ni mueve recibo, puntero o run; devuelve un estado recuperable. Tras relanzar DSH, repetir `bootstrap install` reconoce la composición candidata cargada y completa la misma generación sin redespachar Creator ni reinstalar el nombre estable. Regresiones: instalación fresca aplicada, actualización con roster stale no activa y reanudación posterior al reinicio.

## Gate operativo y carga bundle-local de skills generadas — 2026-09-27

- Hallazgo del piloto Syncify: el `agent.cordis.yml` generado contenía solo persona; el preset Auditor exponía únicamente `workflow_write` y se negó correctamente a operar sin lectura ni bash. El validador Host exige ahora en cada modo persona, bash, fs, fs-search, skill-filesystem y tool-skill, y rechaza filas de subagente/delegación, workflow, web/red y plugin-manager. También valida frontmatter mínimo (`name` exacto al directorio y `description` no vacía) en skills y modos. La transacción copia todas las skills con recursos y cada `SKILL.md` de modo a `bundle/skills/<name>`, rechaza colisiones/symlinks/entradas no regulares, fija `includeDefaultRoots: false` y el `customSkillDirs` absoluto bundle-local en cada preset, y conserva ambos IDs en el recibo. El prompt Creator explicita el contrato. Regresiones cubren composición persona-only, plugins prohibidos, frontmatter, recursos, colisiones y symlinks.

## Presets migrados del directorio legacy a bundles del runtime vigente — 2026-09-27

- Sexto hallazgo del piloto limpio: DSH 0.1.7-rc.2 declara explícitamente que `$DSH_HOME/.agent-presets` ya no se lee; `agentPresets/list` se alimenta de declaraciones ordinarias `@deepseek-ai/dsh-agent-preset` instaladas como bundles de perfil. La transacción escribía correctamente los cuatro archivos de cada modo en la ruta obsoleta, pero el roster solo mostraba los cuatro presets built-in y el rollback retiraba los directorios recién copiados. El Host materializa ahora un bundle gestionado determinista bajo el workspace (`package.json` + `cordis.patch.yml` con una declaración por modo), lo instala/habilita mediante `pluginManager/installBundle`, verifica ambos IDs en `agentPresets/list` sin `broken`, registra nombre/ruta/hash/IDs en un recibo v2 y lo retira vía `pluginManager/removeBundle` en rollback/uninstall. La validación contra DSH real confirmó ambos presets Syncify en el roster actual. Se eliminaron regresiones específicas del almacenamiento legacy y se sustituyeron por bundle, roster, rollback, reintento e integridad del bundle. Suite completa en verde.

## Cookie y puerta de proveedor independientes de settings.yaml (migración del runtime) — 2026-09-27

- Quinto hallazgo del piloto, revelado por el diagnóstico de doble vía: el runtime DSH migró el home (settings.yaml renombrado a settings.yaml.imported, configuración efectiva en profiles/web/cordis.yml) y el guardia de la verificación de cookie exigía settings.yaml existente — «sin intento de cookie» — cayendo siempre al canje, que el navegador auto-abierto consume (401). La verificación de cookie depende ahora de .credentials.yaml (el archivo que de verdad usa), el chequeo post-autenticación acepta settings.yaml o settings.yaml.imported como evidencia de home, y la puerta de proveedor lee el home migrado como respaldo con la misma estructura (nombres de variables, nunca valores). Regresiones: verificación de cookie en home sin settings.yaml; dsh_provider_status sobre settings.yaml.imported. Suite completa en verde (481).

## Reanudación de la finalización Host repitiendo install — 2026-09-27

- Cuarto hallazgo del piloto limpio: la finalización standalone (`finalize`) no completa la identidad del workspace, así que un run GENERATED que llegó con la identidad ausente quedaba atrapado — `install` no re-finalizaba runs GENERATED y `finalize` fallaba con el `FileNotFoundError` crudo; el usuario no tenía un comando de recuperación único. `install` reanuda ahora la finalización Host cuando el run está en GENERATED (sin re-despachar al Creator, idempotente, con el mismo reporte `Host: <estado>` de la cadena de despacho); como la escritura de identidad es previa al escaneo de runs, repetir el mismo comando `bootstrap install` recupera el run de punta a punta. Regresiones: reanudación llama a finalize una vez y reporta ACTIVE; el fallo de finalize se reporta como FINALIZATION_FAILED recuperable. Suite completa en verde.

## Instancia DSH desprendida del lanzador y ventana de asentamiento de cookie — 2026-09-27

- Tercer hallazgo del piloto limpio: el DSH lanzado por `bootstrap` moría con el grupo de procesos del lanzador (contradiciendo «la instancia queda activa») y la verificación de la cookie HMAC corría una sola vez justo tras imprimir la URL — el listener RPC aún no aceptaba, la verificación caía al canje de token (401) y el lanzamiento se declaraba fallido dejando un hijo node huérfano que `process.kill()` del wrapper npm no alcanzaba. Cambios: `launch_dsh_web` crea el hijo con `start_new_session=True` (sobrevive al fin del lanzador); `_terminate_process` mata el grupo de procesos cuando el hijo lo lidera (wrapper + nodo, sin huérfanos); la verificación de cookie obtiene una ventana de reintento (`DSH_AUTH_SETTLE_SECONDS`, 45 s) antes del canje; los tres puntos de fallo del lanzamiento usan ahora la terminación por árbol. Regresiones: reintentos de cookie hasta verificar sin canje, terminación de árbol en fallo de autenticación, kill de grupo real sobre proceso desprendido; cinco tests de lanzamiento fijan la ventana a 0 para mantener determinismo. Suite completa en verde.

## Reutilización de instancia DSH viva en la adquisición sin lanzamiento — 2026-09-27

- Segundo hallazgo del piloto limpio: la vía de adquisición sin `--launch-dsh` verificaba cada candidato con `exchange_token()` — el canje del token de consola de un solo uso — que falla siempre contra una instancia ya autenticada; `finalize` no podía reutilizar una instancia DSH viva y sana jamás (el mensaje además enmascaraba el fallo real reportando solo el último candidato). La reutilización verifica ahora primero la cookie HMAC del home con un RPC barato (`list_sessions`), dejando el canje como respaldo para homes sin cookie vigente — el mismo orden que ya usaba la vía de lanzamiento; el error final incluye el home probado. Regresiones: `test_acquire_reuses_running_instance_without_token_exchange`; `test_acquire_dsh_client_fails_closed_without_session` aislado de los candidatos reales del mantenedor (dependía de que no hubiera instancia viva). Suite completa en verde.

## Identidad de workspace auto-reparada en install — 2026-09-27

- Primer hallazgo del piloto limpio local (Syncify, instalación de principio a fin): con un directorio de workspace pre-creado vacío, `install` solo escribía `project.json` en la rama de creación, así que la finalización Host falló con `FileNotFoundError` crudo sobre la identidad **después** de que el Creator consumiera una generación completa — el run quedó recuperable pero el fallo llegó tarde y sin mensaje accionable. `install` completa ahora la identidad siempre que el workspace exista sin `project.json` (idempotente, con el mismo chequeo de conflicto de nombre), cubriendo directorios pre-creados y restos de fallos parciales. Regresión: `test_preexisting_empty_workspace_gets_identity`. Suite completa en verde.

## Auditoría y reconciliación de la documentación — 2026-09-27

- Barrido de toda la documentación informativa contra el estado comprobado, con los roles de cada documento explícitos: `ARQUITECTURA_FLUJO_AGENTES.md` (diseño normativo), `PLAN_IMPLEMENTACION.md` (índice de progreso), `docs/status.md` (hechos), `docs/usage.md` (uso operativo), `docs/setup-dsh.md` (preparación DSH), `docs/creator-preset-spec.md` (contrato generacional). Corregidos: cabeceras que afirmaban que la capa 3.0 «sigue pendiente» o «no implementada» (usage, arquitectura, plan, START); §7-B3 de la arquitectura ahora documenta el diseño real de adquisición y ciclo de vida de la sesión DSH (adquisición por cookie HMAC, binding al workspace vía `workspaceId`, overlay del plugin, puerta de proveedor por aviso, anti-escalada con relevo) y B5 registra la aceptación determinista con publicación y roster de presets verificados; `docs/usage.md` reescrito por completo con el flujo automático de `bootstrap.py` (subcomandos reales incluidos `verify-acceptance`/`finalize`), estados de run, herramientas de mantenimiento y reglas de «qué no hacer»; `START.md` eliminado por obsoleto y duplicado del README (regresión de consistencia actualizada; su guía de «qué no hacer» vive en usage); `docs/plans/README.md` marca los planes C0–C7 como ejecutados; el borrador de orquestación externa referencia v3.0; status y plan incorporan la sección post-C7 con las unidades de hardening (biblioteca, despacho, binding de workspace, anti-escalada con schemas sin campos de escalada, transacción con veredicto, aceptación Host aislada, presets DSH) y el piloto tardis EN CURSO; el recuento de pruebas deja de fijarse en docs que envejecen (remite a CHANGELOG). Conciliado con el trabajo paralelo ya publicado (instalación de modos como presets, aceptación con evaluador/revisor aislados). Suite completa: 476 pruebas OK (3 skips).

## Overlay workflow-write en el lanzamiento y relevo de delegación — 2026-09-19

- Tercer hallazgo del piloto, en una **sesión delegada**: los subagentes heredan el cwd del padre (una sola carpeta como raíz — con el binding de workspace es la correcta) y su contexto de delegación dice que las aprobaciones se rechazan automáticamente; además el runtime upstream rechaza todo write con `sandbox_permissions` igual al modo vigente («not strictly wider», defecto M7) — combinación que deja cada escritura de subagente en callejón sin salida y la generación sin paquete. El Creator por su parte cumplió el invariante: no escaló, no work-around, no ejecutó accept, reportó limpio. Cambios: (1) el lanzamiento aplica ahora el overlay `scripts/dsh-plugins/cordis-patch.yml` vía `dsh web --patch`, que carga `workflow-write.mjs` — mismo modo → política vigente, sin tocar el home DSH ni instalar dependencias; composición validada offline con `dsh web --dump-config --patch` contra el binario real; escapatoria `DSH_PLUGIN_PATCH=0`. (2) El prompt incorpora el invariante 9: usar `workflow_write` para escribir y relevar en cada tarea delegada la prohibición de `sandbox_permissions`/`justification` (los subagentes no ven el prompt del Creator). Registro de tools: un patch no puede reemplazar `write` (nombre duplicado lanza error), por eso el fix es tool adicional + relevo. Suite completa: 364 pruebas OK (2 skips previos).

## Invariante anti-escalada total en el prompt de Creator — 2026-09-19

- Segundo hallazgo del piloto: tras las denegaciones iniciales, la sesión pidió `danger-full-access` con justificación literal «placeholder» para un comando **de solo lectura** (`pwd && git rev-parse && git status`). La causa está en el runtime: la descripción del tool bash instruye al modelo que «escalar de entrada está bien cuando esta sesión ya denegó el mismo acceso», y el marcador de denegación sugiere reintentar con `sandbox_permissions` — el modelo generaliza y escala preventivamente con justificaciones de relleno. El invariante 8 sube de «no pedir danger-full-access» a prohibición total del canal: jamás enviar `sandbox_permissions` ni `justification`, con ningún valor; la guía de escalada del runtime no aplica a esta misión, una denegación indica intento fuera de alcance y se reporta como hallazgo. Regresión: el prompt contiene la prohibición del campo. Suite completa: 362 pruebas OK (2 skips previos).

## Sesión de Creator ligada al workspace del run — 2026-09-19

- Hipótesis del piloto confirmada contra el runtime DSH (0.1.5-rc.1): `session/create` acepta `workspaceId` o `cwd`, no ambos; con solo `cwd` la sesión no se adjunta al registro de workspaces (aparece «Ungrouped» en la UI) y su frontera de `workspace-write` queda reducida al directorio del run — cualquier escritura a nivel workspace se deniega y empuja a escaladas. El despacho registra ahora el workspace del run (`workspace/create`, idempotente) y crea la sesión con `workspaceId`: la sesión queda agrupada bajo el nombre del workspace y su cwd — la raíz escribible del modo vigente — es el workspace entero, que es el área de escritura diseñada del Creator. La decisión se apoya en el código del runtime: `SandboxPolicyService.resolve` toma `session.header.cwd` como `workspaceRoot`, y `createOrAdopt` lo fija desde `workspace.path`. Regresiones: los despachos pasan la raíz del workspace y la RPC crea workspace + sesión sin clave `cwd`. Suite completa: 362 pruebas OK (2 skips previos).

## Invariante anti-escalada en el prompt de Creator — 2026-09-19

- Hallazgo real del piloto tardis: la sesión de Creator pidió `danger-full-access` para escribir un archivo de prueba en el workspace del run, con justificación circular («tool schema conflict»). El prompt versionado incorpora el invariante 8: no solicitar escaladas de sandbox — el área del run es escribible bajo `workspace-write`; una escritura denegada o un conflicto de esquema es un hallazgo que se reporta y reproduce en modo vigente, nunca un motivo de escalada. Coincide con la política vigente (`setup-dsh.md`: strictly-wider exige aprobación real; el error de esquema no autoriza `danger-full-access`). Regresión: el prompt contiene la prohibición.

## Autenticación de lanzamiento por cookie HMAC del home — 2026-09-19

- El 401 del canje tiene causa identificada: el token de consola es de un solo uso y compite con el navegador que `dsh web` auto-abre — quien llega primero lo consume. La autenticación del lanzamiento prefiere ahora la cookie HMAC duradera de `~/.dsh/.credentials.yaml` (`from_dsh_home` con el puerto del URL observado), verificada con un RPC barato (`list_sessions`) antes de usarse; el canje con reintentos queda como respaldo cuando el home no aporta credenciales. Si ninguna vía verifica, el hijo se detiene y el run queda recuperable con la causa. Suite completa: 361 pruebas OK (2 skips previos).

## Canje de token tras el lanzamiento de DSH — 2026-09-19

- El despacho seguía sin ocurrir tras un lanzamiento exitoso: `launch_dsh_web` entrega el cliente con la URL de token de un solo proceso, pero `authenticated` permanece `False` hasta canjear el token por la cookie de autoridad, y `run_creator` no despacha a clientes no autenticados — dejaba el hijo DSH corriendo sin usarlo. La ruta de lanzamiento ejecuta ahora `exchange_token()` tras el arranque (con kill del hijo si falla) y el despacho procede. Regresión: el canje ocurre una vez y el hijo no se mata. Suite completa: 361 pruebas OK (2 skips previos).

## Llave ausente: aviso y continuar, parada solo estricta — 2026-09-19

- La evidencia de tardis invierte la política de la puerta: con DSH configurado, **ninguna** llave de los ocho proveedores estaba en el entorno y sin embargo DSH funciona ahí — el entorno no es la única fuente de llaves (dotenv, keychain, credenciales de UI). Una llave ausente ya no bloquea: se despacha con `aviso:` explícito registrado en el resultado y en el run; si Creator falla por autenticación, el run queda `RETAINED` con la causa real. `DSH_PROVIDER_STRICT=1` restaura la parada dura para entornos que quieran la garantía solo-entorno. La resolución de proveedor utilizable se mantiene como diagnóstico (indica cuál resolvió o qué falta por proveedor). Corregido además un anidamiento de tupla en la rama estricta que devolvía `(client, (None, razón))`. Suite completa: 360 pruebas OK (2 skips previos).

## Reconocimiento del binario dsh de npx — 2026-09-19

- El guardia de puerto clasificó como ajeno a un DSH legítimo: el cmdline de una instalación vía npx es `node .../node_modules/.bin/dsh web`, sin el scope `@deepseek-ai/dsh` en la ruta. Además, el stop anterior mató al wrapper `npm exec` (matcheable) dejando huérfano a su hijo `.bin/dsh` con el puerto — causa exacta del `EADDRINUSE` observado. Nuevo clasificador común `_is_dsh_web_cmdline`: reconocen DSH web tanto las rutas del registry como cualquier ejecutable con basename `dsh`, siempre con indicador web (` web`/`--profile web`); lo usan por igual el buscador de PIDs y el guardia de puerto. Regresión dedicada con el cmdline exacto de tardis. Suite completa: 359 pruebas OK (2 skips previos).

## Propiedad del puerto 3080 en el lanzamiento — 2026-09-19

- El diagnóstico del fallo real identificó `EADDRINUSE` en 3080: un escucha que el patrón de PIDs no capturó o un puerto sin liberar. La ruta de lanzamiento ahora es dueña del puerto: tras detener las instancias detectadas, `_ensure_port_free_for_dsh` resuelve el escucha del puerto vía `ss`; si su cmdline es de DSH lo detiene y reintenta hasta el plazo, y si es un proceso ajeno se niega nombrando PID y comando — nunca mata procesos foráneos a ciegas. Regresiones: parseo de `ss`, puerto libre, escucha DSH rezagada, escucha ajena y lanzamiento con puerto bloqueado. Suite completa: 357 pruebas OK (2 skips previos).

## Lanzamiento DSH no interactivo con diagnóstico — 2026-09-19

- `launch_dsh_web` ya no falla a ciegas: captura la salida de DSH y la incluye en el error con cualquier token redactado, además de exponer el código de salida. La causa más probable del fallo observado ("Ok to proceed?" de npx abortando sin TTY) se elimina con `npx -y` y `stdin` nulo; el plazo de arranque es de 120s y `DSH_MODULE_ROOT`/instalación local siguen siendo responsabilidad del titular. Regresiones con proceso falso: éxito con URL, fallo con salida capturada y redacción de tokens. Suite completa: 352 pruebas OK (2 skips previos).

## Resolutor de proveedor utilizable — 2026-09-19

- La puerta de proveedor ya no exige la llave de un proveedor concreto (era ilusorio: ningún usuario debe tener la misma configuración). `dsh_provider_status` resuelve el primer proveedor utilizable recorriendo los declarados en settings.yaml — primero el default de DSH (el último modelo que el usuario configuró), después el resto en orden de configuración — y acepta cualquiera con modelos cuya variable de llave esté presente (verificación solo por nombre, valores jamás leídos ni registrados). Si no hay ninguno utilizable, se detiene enumerando qué variable falta por proveedor, con una sola acción concreta para el titular.
- Regresiones: fallback cuando la llave del default falta, default desconocido con fallback, parada con lista completa de variables ausentes, y las rutas de lanzamiento/sesión existente con el resolutor. Suite completa: 349 pruebas OK (2 skips previos).

## Reanudación del despacho en runs existentes — 2026-09-19

- `bootstrap install` sobre un run ya existente ya no se limita a `EXISTING`: con el despacho activo (comportamiento por defecto del CLI) reanuda la generación para los estados reanudables por Creator (`CREATED`, `GENERATING`), aplicando la adquisición de sesión, la puerta de llave y la supervisión. Los estados propiedad del Host (`GENERATED` en adelante) nunca se re-despachan, y los estados intermedios no reanudables (`DISCOVERING`, `DESIGNING`, `REPAIRING`) quedan en `EXISTING` porque despacharlos retendría el run indebidamente. La cadena de despacho se extrajo a `_dispatch_creator_chain`, compartida por run nuevo y existente. Suite completa: 348 pruebas OK (2 skips previos).

## Ciclo de vida DSH y puerta de llave API — 2026-09-19

- Puerta de proveedor fail-closed antes de despachar: `dsh_provider_status` lee la estructura de `settings.yaml` del home de DSH (proveedor por defecto en `agent-default-model`, su `apiKeyEnv` y modelos) y verifica que la variable de llave exista en el entorno — solo el NOMBRE, jamás el valor, incluida la inspección por nombre del entorno de instancias DSH en ejecución vía `/proc`. Sin proveedor, sin modelos o sin llave, el despacho se detiene con la pieza concreta que falta; ninguna clave se lee, copia ni registra.
- La ruta de lanzamiento (`--launch-dsh`) es dueña del ciclo de vida de DSH: detecta instancias DSH web en ejecución por comando exacto (`@deepseek-ai/dsh` con `web`/`--profile web`), las detiene (SIGTERM, espera, SIGKILL de respaldo, PIDs como evidencia) y arranca una instancia fresca con la configuración vigente. Si la puerta de llave falla tras arrancar, el hijo se detiene y el run queda recuperable con el aviso.
- Implementado contra la configuración real observada (`~/.dsh/settings.yaml`, proveedores con `apiKeyEnv`); regresiones con fixtures de home DSH: estado del proveedor con/sin llave, detección de PIDs exacta, escalada de señales, y las cuatro rutas de adquisición (lanzamiento con llave, lanzamiento deteniendo instancia previa, lanzamiento con llave ausente que mata al hijo, sesión existente sin llave). Suite completa: 346 pruebas OK (2 skips previos).

## Despacho automático de Creator — 2026-09-19

- `creator_client.run_creator` adquiere la sesión DSH local por sí misma cuando se le pide (`acquire=True`): cliente inyectado, variable `DSH_HOME` o casas estándar (`~/.dsh`, `~/.deepseek`, `~/.config/dsh`), verificando que el servidor responda al intercambio de token; con `--launch-dsh` arranca `dsh web` como hijo (nunca descarga DSH por iniciativa propia). Sin sesión autenticada devuelve `PREPARED` con la acción concreta, en estado recuperable.
- Tras despachar, supervisa la generación dentro del presupuesto (poll de `generated/` y estado del run) y verifica el paquete al completarse; el agotamiento del presupuesto retiene con causa o deja el run reanudable, nunca en estado silencioso.
- `bootstrap install` encadena el despacho automáticamente desde el CLI (`--no-dispatch` para solo preparar; `--launch-dsh` para arrancar DSH). El resultado de Creator se incrusta en la salida de install; un fallo de despacho mantiene el run creado y recuperable. La función Python `install()` sigue sin despachar por defecto (comportamiento de tests y programático invariante).
- Suite completa: 336 pruebas OK (2 skips previos). Incluye regresiones de adquisición fail-closed, despacho vía adquisición y encadenado de install con Creator inaccesible.

## Biblioteca integrada en el pipeline Creator y refuerzos fail-closed — 2026-09-19

- `bootstrap install` congela un snapshot de `library/library.json` validado en `run/inputs/library.json` y registra su SHA-256 en `bootstrap-request.json`: la selección de Creator queda anclada a la biblioteca exacta del run, como procedencia.
- El prompt versionado de Creator (`creator_client.build_creator_prompt`) incorpora la sección "Biblioteca disponible" generada fail-closed desde la biblioteca materializada: las 21 skills base con propósito y aplicabilidad, los 4 patrones de catálogo con sus criterios de activación y el digest del documento. Biblioteca ausente o inválida detiene la construcción del prompt.
- Contratos de modos y skills incorporan `reuse_reference`: reutilizar `base-library` o `specialized-catalog` exige nombrar la entrada exacta; declarar `extension` prohíbe el campo. Esquemas espejo (`skills.schema.json`, `modes.schema.json`) actualizados.
- La capa de contratos del validador Host ya no es solo estructural: valida los documentos de contrato del paquete contra su schema y resuelve cada `reuse_reference` contra el snapshot de biblioteca del run; una referencia inexistente produce RETAINED.
- `transaction.install` exige un veredicto Host explícito ACTIVE (acceptance/host-verdict.json, ruta o diccionario) vinculado a la misma generación; activar sin aprobación del Host falla cerrado, y el CLI incorpora `--host-verdict`. No existía ningún llamador además de los tests, así que el gate no tiene bypass silencioso.
- `bootstrap`: la derivación de `root_identity` se extrae a `_root_identity` y la comparten `install` y `update`; antes `update` comparaba el revision Git crudo contra una identidad que podía ser un digest de revision corto o de la ruta, produciendo drift falso o no-op falsos.
- Suite completa: 331 pruebas OK (2 skips previos).

## Coherencia documental de C0–C7 — 2026-09-19

- README y `docs/creator-preset-spec.md` dejan de describir C0–C7 como pendiente: el estado refleja la implementación verificada (bootstrap, Creator, validador Host, aceptación, transacción, promoción) sin afirmar autonomía de extremo a extremo sin sesión DSH real configurada por el usuario. La biblioteca materializada (21 skills base, 4 patrones de catálogo, registro de fuentes) se documenta como parte de la distribución.

## Catálogo ampliado: tres patrones evidence-gated y pin de estándares — 2026-09-19

- Añadir tres `catalog_pattern` a `library/library.json` con contenido en `library/catalog/`: `web-accessibility-wcag-audit` (dominio `web-frontend`), `http-security-headers-verifier` (dominio `web-platform`) y `aws-iam-policy-static-review` (dominio `aws-security`). Todos con activación solo por señales observables, invariantes de solo lectura, distinción declarado/efectivo y resultado de inventario de hallazgos, no de conformidad. Nueve escenarios (SC-147…SC-155) con guardas de conformidad por herramienta, afirmación sin contexto de despliegue, wildcard sin marcar y uso de credenciales.
- Pin de estándares versionados: `source-registry.schema.json` y `library.schema.json` incorporan `spec_version` opcional; un estándar se considera fijado por su versión de especificación (con fecha de observación) y un repositorio sigue exigiendo commit. El validador exige commit o `spec_version` en la procedencia de toda entrada seleccionable.
- Fuentes fijadas por observación directa (2026-09-19): `wcag-22` por versión de especificación (2.2, W3C Recommendation publicada 2024-12-12, URI fechada), `mdn-web-docs` por instantánea de `mdn/content` y `aws-waf-apg` por instantánea de `awsdocs/iam-user-guide`.
- Regresiones: corpus nuevo del registro (pin por spec_version aceptado, pin sin ancla rechazado, fecha exigida), procedencia de biblioteca sin pin rechazada, y atribución de licencia exigida en la sección Procedencia sea cual sea la licencia de origen. Suite completa: 316 pruebas OK (2 skips previos).

## Primer patrón de catálogo con activación por evidencia — 2026-09-19

- Añadir el primer `catalog_pattern` a `library/library.json`: `fastapi-openapi-contract-check` (dominio `python-backend`), contenido en `library/catalog/fastapi-openapi-contract-check/SKILL.md` con cuatro escenarios (SC-143…SC-146: positiva, activación sin evidencia → BLOCKED, capability-denial de llamada a servicio real → BLOCKED, esquema no reproducible → NOT_COVERED).
- Activación solo por señales observables: fastapi/pydantic en dependencias, routers/BaseModel/OpenAPI observados, encargo explícito de contratos. Comprobación de solo lectura sobre OpenAPI reproducible con versiones fijadas; sin llamadas a servicios reales ni inferencia de seguridad desde el esquema; el resultado es un inventario de diferencias clasificadas, no un sello de conformidad.
- Registro de fuentes: `fastapi-pydantic-docs` (unpinned) se sustituye por `fastapi-framework` y `pydantic-framework`, ambas fijadas por observación directa (`git ls-remote` de fastapi/fastapi y pydantic/pydantic, 2026-09-19). Registro en 43 fuentes.
- Regresiones de biblioteca extendidas al catálogo: procedencia solo de fuentes registradas con commit completo, cobertura bidireccional skill/patrón↔escenario, presupuesto y saneamiento, y acoplamiento verbatim entre criterios de activación declarados y contenido del patrón. Suite completa: 311 pruebas OK (2 skips previos).

## Biblioteca base completa: segunda ola de skills — 2026-09-18

- Segunda ola convertida desde `addyosmani-agent-skills` (reimplementación propia, atribución MIT, commit fijado): `context-engineering`, `api-and-interface-design`, `observability-and-instrumentation`, `documentation-and-adrs`, `performance-optimization`, `incremental-implementation`, `code-simplification`, `deprecation-and-migration`. La biblioteca base queda completa con 21 skills; los 29 candidatos de las fuentes registradas están todos contabilizados (21 convertidos, 5 plegados en la primera ola, 3 rechazados como meta/interactivos).
- 16 escenarios nuevos (SC-127…SC-142) validados contra `scenario.schema.json`, incluyendo un `prompt-injection` para la frontera dato/instrucción de context-engineering y guardas de big-bang, borrado directo y optimización sin medición. Regresión de biblioteca endurecida: el suelo de skills base pasa de 13 a 21. Suite completa: 309 pruebas OK (2 skips previos).

## Biblioteca base materializada: primera ola de skills — 2026-09-18

- Añadir `library/library.json` (documento de biblioteca validado contra `library.schema.json`) y el contenido de las skills base en `library/base/<skill>/SKILL.md` con escenarios en `library/base/<skill>/scenarios/`.
- Primera ola convertida desde fuentes registradas (`obra-superpowers`, `addyosmani-agent-skills`), reimplementación propia con atribución MIT y commit fijado: `brainstorming`, `writing-plans`, `executing-plans`, `systematic-debugging`, `test-driven-development`, `requesting-code-review`, `receiving-code-review`, `verification-before-completion`, `finishing-a-development-branch`, `spec-driven-development`, `constraint-driven-development`, `source-driven-development`, `security-and-hardening`. Cada skill declara cuándo aplica, procedimiento, invariantes, prohibidos/límites, escenarios y procedencia; entrada única ≤ 32 KiB.
- Plegados en la conversión: `planning-and-task-breakdown`→`writing-plans`, `debugging-and-error-recovery`→`systematic-debugging`, `test-driven-development` (addyosmani)→`test-driven-development`, `code-review-and-quality`→`receiving-code-review`, `doubt-driven-development`→`verification-before-completion`. Quedan para la segunda ola: context-engineering, api-and-interface-design, observability-and-instrumentation, documentation-and-adrs, performance-optimization, incremental-implementation, code-simplification, deprecation-and-migration. Rechazadas como base: idea-refine, interview-me, using-agent-skills (meta/interactivas).
- 26 escenarios nuevos (uno positivo y al menos uno FAIL/BLOCKED por skill) validados contra `scenario.schema.json`; 13 escenarios negativos usan tipos específicos (scope-violation, write-violation, idempotence). Añadir `tests/test_library_base.py` (15 pruebas): documento válido, procedencia solo de fuentes registradas con commit completo, cobertura bidireccional skill↔escenario, presupuesto de entrada, frontmatter coherente, sin sombra de las skills MVP ni nombres legacy, contenido saneado y atribución presente. Suite completa: 309 pruebas OK (2 skips previos).

## Registro de fuentes de skills y biblioteca endurecida — 2026-09-18

- Añadir `schemas/source-registry.schema.json` y `library/source-registry.json`: registro canónico de 42 fuentes externas evaluadas (20 repositorios de skills/índices/runtimes y 22 estándares o guías institucionales/de dominio) con URL canónica, commit fijado, fecha de observación, licencia, estado (`REFERENCE`/`CANDIDATE`) y decisión razonada. Política de adquisición fail-closed: solo pin manual, sin auto-instalación (npx/marketplace/descargas), staging fuera del árbol canónico y validación Host previa a la activación. El inventario pormenorizado de 11.407 entradas que respalda las decisiones permanece fuera del árbol; el registro conserva solo su SHA-256.
- Endurecer `library.schema.json` y su validador: un patrón de catálogo exige criterios de activación observables, invariantes y escenarios; una skill base exige escenarios; la procedencia exige `license` y `source` (`internal` o `source_id` del registro). Una entrada sin estos requisitos no es seleccionable y la regeneración cae a la capa inferior o a `RETAINED`.
- Añadir `validate_source_registry` al contrato generacional: rechaza fuentes remotas sin URL/commit/fecha, candidatas sin pin o con licencia no resuelta, políticas relajadas, IDs duplicados, hashes inválidos y rutas locales en metadatos. Corpus nuevo de 23 pruebas positivas y negativas; el archivo de registro real se valida dentro de la suite. Suite completa: 294 pruebas OK (2 skips previos).

## Estrategia híbrida de skills aprobada — 2026-09-16

- Registrar la decisión: Creator reutiliza primero una biblioteca base inmutable y un catálogo de patrones especializados, luego compone y aplica overrides declarativos; solo genera extensiones como último recurso con contrato, escenarios y aceptación específica. Una skill transferida debe aceptarse en cada proyecto destino.
- Reflejar el orden obligatorio en arquitectura, contrato generacional, README/status/usage, planes C0/C2 y protocolo de adaptación. La regresión exige declarar reutilización antes de generar o aceptar una extensión.

## Planes de implementación C0–C7 — 2026-09-16

- Añadir `docs/plans/`: mapa/gobierno, un plan detallado por C0–C7 y protocolo transversal de adaptación. Los planes descomponen la arquitectura aprobada sin crear un backlog paralelo; `PLAN_IMPLEMENTACION.md` sigue siendo el único índice de estado.
- Cada plan define artefactos, schemas, dependencias, gates positivos/negativos, adaptación autorizada, checkpoints y límites. Los planes dejan espacio para cambiar pasos por evidencia, pero un cambio contractual requiere actualizar primero la arquitectura.

## Limpieza canónica completa — 2026-09-16

- Eliminar físicamente del árbol canónico todos los documentos, diagramas, modos genéricos y tests legacy sustituidos por arquitectura 3.0/C0–C7. Git conserva el historial; el árbol actual ya no contiene una segunda norma operativa.
- Conservar solo cinco skills generales, servicios Host, contratos de auditoría/evidencia, plugin `workflow-write` y regresiones permanentes. Presets de proyectos y procedimientos MVP no forman parte del conjunto distribuible actual.
- Eliminar `cycle-artifacts.md` después de conservar sus invariantes en arquitectura/servicios C0–C7; retirar tests de launchers/preset mapping ligados a layouts externos.
- Ampliar `test_architecture_consistency.py` para exigir ausencia física de assets legacy, referencias operativas obsoletas y rutas del mantenedor.

## Limpieza canónica: eliminar artefactos legacy del árbol — 2026-09-16

- Eliminar del árbol versionado 21 archivos legacy que ya no forman parte de la arquitectura 3.0: tres planes históricos (P0–P9, M1–M8, evaluación F1–F5), diez diagramas v2.4 y su índice, tres skills operativas universales del MVP (`workflow-auditor`, `workflow-complete-auditor`, `workflow-continuous-repair`), checklist de trial-readiness, contrato de ciclo-artefactos, test de launchers personales y test de preset mapping externo. Git conserva todo el historial.
- Reescribir START para no despachar modos genéricos eliminados; solo prepara workspace y remite a C0–C7. Reescribir status como estado vigente conciso sin narrativa v0.1/v2.4. Corregir arquitectura 3.0 donde todavía describía creator-preset-spec como experimento anterior.
- Regresión documental reescrita: exige ausencia física de archivos legacy, ausencia de referencias a planes/diagramas/modos eliminados en documentos operativos, y ausencia de rutas del mantenedor.
- Conjunto canónico actual: arquitectura 3.0, C0–C7, contrato generacional, 5 skills generales, servicios Host, plugin workflow-write, contratos de auditoría y evidencia, y regresiones técnicas/documentales.

## Auditoría de vigencia documental 3.0 — 2026-09-16

- Auditar archivos versionados para impedir que instrucciones v2.4/v0.1 se interpreten como vigentes. Corregir AGENTS/START/skills del MVP, runbook, status, evaluación externa, planes históricos y guía de diagramas.
- Los procedimientos `workflow-auditor`, `workflow-complete-auditor` y `workflow-continuous-repair` quedan rotulados como fixtures/fuentes normativas del MVP, no modos finales; ausencia de `workflow_write` retiene antes de escribir (sin fallback por bash).
- Neutralizar planes P0–P9 y M1–M8 con marcadores locales `NO EJECUTAR`; C0–C7 es el único backlog. Parametrizar el test externo de launchers y rutas de diagramas.
- Añadir `tests/test_architecture_consistency.py` para detectar regresiones de vigencia, presets genéricos, v0.1 en skills, rutas del mantenedor y fallback de escritura.

## Arquitectura 3.0 promovida — 2026-09-16

- Promover el diseño aprobado como `ARQUITECTURA_FLUJO_AGENTES.md` v3.0 y retirar el documento candidato para mantener una sola norma. El MVP anterior permanece como base comprobada; la experiencia final de un comando queda pendiente en C0–C7.
- Corregir el flujo de incorporación: usuario configura DSH/proveedor una vez; `bootstrap install` prepara workspace y llama automáticamente a Creator; Creator usa capacidades internas de discovery/design/test/generation y genera `<Proyecto>-auditor`, `<Proyecto>-continuous-repair` y skills específicas; Creator invoca `accept`; solo Host valida, respalda, instala, acepta/retiene y promueve/rollback.
- Reemplazar la especificación de «preset neutral de dos archivos» por el contrato generacional completo (`creator-runs`, manifests, contracts, scenarios/holdouts, validation, backup, promotion y drift). Presets Syncify/RehabWeb quedan como fixtures históricos, no defaults.
- Adaptar integralmente patrones de las nueve skills de `jsmastery-pro/skills` (MIT, commit observado `43b69e4`): scope particiona; audit descubre; architect diseña contratos; document normaliza; test deriva escenarios; develop genera; check verifica/revisa; debug repara RETAINED; sync detecta drift. No se adoptan sus modos finales, slash workflow, npx/MCP auto-install ni dependencias Claude/web/Git.
- Abrir C0–C7 como único backlog vigente: schemas/fixtures, install, automatización Creator, validador Host, transacción/backups, aceptación automática, pilotos clean-room y distribución de piloto.

## MVP del framework aceptado — 2026-09-13

- Cerrar el MVP tras consumir la cola finita de 17 unidades en dos proyectos: 17 auditadas, 3 aceptadas con `missions.verify` vigente y reauditoría semántica CONFIRMED, 14 retenidas con causa/evidencia, cero estados silenciosos. La aceptación corresponde al framework y su comportamiento fail-closed, no a declarar los productos libres de defectos.
- Demostrar el controlador Host en una unidad real y M6 mediante `docker kill` durante `TURN_STARTED`: presupuesto preservado, reconciliación a PENDING, sin publicación duplicada. Límite: pérdida de energía no ensayada sin hipervisor.
- Correcciones semánticas finales en ramas de producto: Syncify archive/dependency rollback recuperable y ejecución segura (16+13 tests); RehabWeb agenda/evaluaciones endurecidas (82 tests). Reauditorías finales CONFIRMED y ramas publicadas.
- Suite final del framework 64 tests OK; archivos finales restaurables con checksums (80/94 archivos). RSI y F1–F5 quedan post post-MVP.

## Tanda MVP: controlador real y consumidor de cola — 2026-09-13

- `host_controller`: `update_unit_refs` para launchers que materializan recibos durante el turno (regresión incluida). El controlador condujo su primera unidad real de punta a punta (turno del rig → verificación de hashes → lote del publicador → UNIT_DONE) con suites en verde: M3 acreditado en real para el ciclo mecánico.
- Driver de misión externo (herramienta de ensayo, fuera del árbol): consume la cola por unidades con auditorías paralelas y reparaciones secuenciadas; integra cada unidad aceptada en la rama `workflow-repairs` del producto con commit+push. Unidades aceptadas e integradas: Syncify 5, RehabWeb 4 (suite 77 tests OK). Excepción declarada: auth-bridge RETAINED por QA fork sin session_id (2 intentos) — hallazgo de runtime registrado (no expone el id del subagente fork).
- M8 acreditada: distribución del framework por red (clean-room desde el origen privado autorizado).

## Distribución por red del framework (M8) — 2026-09-13

- Con el origen privado autorizado por el titular, acreditada la distribución por red: clon clean-room con HEAD verificado, bootstrap desde el clon (idempotente), carga nativa 8/8 skills y suite del clon 62 tests OK. Push del flujo a `origin/fix/local-artifact-integrity` autorizado explícitamente. La publicación pública con licencia queda como opción del titular.

## M7 como plugin y ramas de producto — 2026-09-13

- `scripts/dsh-plugins/workflow-write.mjs` (nuevo): herramienta `workflow_write` con semántica de escalada corregida (mismo modo = política vigente; mayor = aprobación real; denegación fail-closed fuera del área). Resuelta la sonda de plugins: el loader acepta rutas absolutas en filas de preset y exige `inject` + `output {schema, render}`. Montado en los presets del flujo; regresión mecánica `tests/test_workflow_write_plugin.py`. M7 deja de ser bloqueante: el runtime instalado no se parchea y el hallazgo se reportará upstream.
- Ramas `workflow-repairs` en Syncify y RehabWeb (autorización explícita del titular): unidades aceptadas integradas y commiteadas por unidad con referencia a recibos; suites en verde; publicadas en origin. Las futuras unidades de M1/M2 integran allí.
- Decisiones del titular registradas: M6 autorizado; RSI y F1–F5 como plan de mejora posterior al MVP; M8 aclarada (framework: descarga por red + publicación con licencia).

## Tanda M1–M5 con subagentes — 2026-09-13

- Tres servicios nuevos por subagentes (revisados y con regresiones): memoria de decisiones (`scripts/decisions.py`), métricas de misión (`scripts/metrics.py`) y controlador Host (`scripts/host_controller.py`, turn_launcher inyectable, reconciliación idempotente, lock de escritor único y presupuesto durable). Suite completa 61 tests.
- M2 (reauditoría semántica) validado en piloto DSH real: REOPENED correcto ante base obsoleta y CONFIRMED contra el candidato integrado; decisión "reauditar contra la copia integrada" registrada en la nueva memoria de decisiones.
- M1 unidad 3 (`metadata_bridge`): el ejecutor retuvo sin dependencia (`aiohttp`), adquirida host-side con wheels a destino externo, reparación con rojo→verde real, lote `syncify-u3` COMPLETE e integración en copia; suites del conjunto 3/3 en verde.
- Primer consumo del ledger de métricas con datos reales: 24 turnos, 684 requests, ~6,8 M tokens de entrada. `PLAN_IMPLEMENTACION.md` y `docs/status.md` actualizados.

## Plan de pendientes del núcleo — 2026-09-13

- Añadir `docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md`: organización descriptiva de lo restante tras la misión de cierre (M1 cola completa por proyecto, M2 reauditoría semántica propia, M3 controlador Host real, M4 aceptación integral, M5 memoria de decisiones y métricas instrumentadas, M6 durabilidad/descendientes remotos, M7 defecto runtime `write` y M8 distribución/publicación remotas), con base operativa heredada del rig probado, dependencias, trazabilidad y formato de entrega. Documento de planificación; PLAN_IMPLEMENTACION.md sigue siendo el único índice de progreso.

## Misión de cierre integral en copias aisladas — 2026-09-13

- Ejecución real de P0–P9 del plan de cierre por el agente de mantenimiento, con DSH real aislado (launcher + canal + presets + nrouter) sobre copias limpias de Syncify y RehabWeb; evidencia externa en `Improvement-ensayos/mision-arq-20260913/` (recibos, sesiones, lotes, archivo, métricas, UX).
- `scripts/inference_channel.py`: deadline de respuesta convertido en cuota por lanzamiento (default 20 s, tope 300) tras matar turnos reales largos; regresión nueva; arquitectura §11 actualizada.
- `skills/workflow-auditor`, `skills/workflow-continuous-repair`: guía de escritura de evidencia por bash con retención sin aprobación, tras confirmar en rig el rechazo «not strictly wider» de escrituras que piden el modo ya vigente (hallazgo del runtime registrado, no parcheado).
- Resultados: Syncify dos vueltas completas (auditoría→reparación rojo/verde→QA subagente→verify/reaudit→lotes `syncify-u1b`/`u2b` COMPLETE), integración conjunta en copia con suites verdes y archivo restaurable; RehabWeb dos vueltas (alertas 403 a paciente; adaptaciones autorizadas por el terapeuta responsable), 74 tests OK integrados, lotes `rehabweb-u1b`/`u2` COMPLETE y archivo restaurable. Caída real del rig sin huérfanos; métricas y UX registradas externamente.
- Estados actualizados en `PLAN_IMPLEMENTACION.md` (filas 5–8) y `docs/status.md`; siguen PARCIAL: cola completa por proyecto, reauditoría semántica como turno propio, controlador Host real, memoria de decisiones instrumentada y publicación remota sin autorización.

## Deadline de respuesta por lanzamiento en el canal — 2026-09-13

- `scripts/inference_channel.py`: el deadline de respuesta deja de ser el fijo 20 s y pasa a ser cuota por lanzamiento (`DEFAULT_DEADLINE=20`, tope duro `MAX_DEADLINE=300`) con validación idéntica al resto de cuotas. Motivo registrado: en el rig aislado de la misión de cierre integral, el turno real del Auditor sobre la copia de Syncify murió con 502 del receptor tras 35 tool calls cuando una completación con contexto amplio superó el corte histórico; el humo corto no lo ejercitaba. Regresión nueva `test_launch_deadline_per_launch` (default conserva el corte, tope elevable, validación fail-closed de argumentos fuera de rango); suite del canal: 9 tests aprobados. Arquitectura §11 actualizada; el timeout del launcher sigue siendo el límite externo del lanzamiento.

## Plan de cierre integral y evaluación de orquestación externa — 2026-09-13

- Añadir documento de ejecución descriptivo para otro agente, subordinado a la arquitectura y a la matriz de progreso: cierre de todas las capacidades del núcleo con evidencia, continuidad de trabajo y excepción explícita ante bloqueo real de autoridad o recursos.
- Exigir aceptación limpia con Syncify y RehabWeb en entornos externos aislados, desde adquisición/configuración hasta auditoría, reparación, QA, ciclo circular, integración solo en copia y recuperación; interacción principal por mensajes cortos DSH, sin edición manual de recibos ni troubleshooting técnico trasladado al usuario.
- Evaluar las propuestas externas: specs trazables, composición Host y localizadores locales son aprovechables; eventos/remotos e índices avanzados requieren contratos y prueba; Vibe Kanban, clientes alternativos y embeddings no son dependencias obligatorias. Worktree no equivale a sandbox y EARS no verifica semántica.
- Separar recomendaciones de RSI y extensiones de implementación acreditada. Esta entrega solo añade planificación/evaluación documental; no instala, activa runtime ni ejecuta nuevas misiones de producto.

## Onboarding de sesión, cuota de mensajes y reintento F6 — 2026-09-13

- `scripts/inference_channel.py`: tope de mensajes por request configurable por lanzamiento (`DEFAULT_MESSAGES=64`, tope duro `MAX_MESSAGES=256`) en lugar del fijo 64 que mataba los turnos del ejecutor (lote 2: 12 denials `messagesBounds`, messageCount 66); presupuesto, tokens, payload, allowlist y fail-closed sin cambios. Regresiones nuevas incluido el camino real por launcher (130 mensajes: 502 al default, 200 con el tope elevado).
- `skills/workflow-continuous-repair`: una línea mínima que obliga a retener ante el rechazo de esquema de `bash` o «not strictly wider» en un subagente ejecutor (confirmación empírica del escenario (2) de setup-dsh.md con el transcript de la sesión RehabWeb 3081); corrección esperada documentada en setup-dsh.md.
- Reintento F6-DUPLICATE-CONVERSATION-500 en rig aislado (`mission-faseb-b3`, patrón lotes 1/2): ejecutor `nrouter/Subagents-Coding` (mensajes 256, gasto 40/256, 0 denials, messageCount máx 82) con rojo-verde real, QA `nrouter-raw/Subagents-Audits` ACCEPTED en sesión separada, run-check dentro del sobre, `verify`/`reaudit` OK; checkpoint `faseb-003` con la excepción resuelta y producto original intacto (integración solo en copia de ensayo).
- Evidencia de la unidad: onboarding y humo nativo de skills en `/home/alan/DSH-workspace/session-rehabweb-2/evidence/`; canal y lanzamientos en `.../mission-faseb-b3/runs/` (externos al repositorio).

## Arquitectura v2.4 y cobertura verificable — 2026-09-13

- Recuperar memoria de decisiones (identidad, motivo, contrato, sustituciones y revisión QA), métricas finas con fuente/límites y delegación para contener contexto, especializar y contrastar; conservar la prohibición de agentes por apariencia. Corregir la referencia al plan original preservado en archivo externo, sin importar datos privados.
- Incorporar de los modos DSH las dimensiones de falsa completitud y revisión de contratos, inventario/exclusiones exhaustivos, dos perspectivas por unidad, barrido independiente antes de reconciliar, prevención de recurrencia, cifras de fuente vigente y verificación humana necesaria. Actualizar skills existentes sin instalar/sincronizar copias operativas ni cambiar presets, permisos o routing.
- `scripts/audit.py`: snapshot determinista SHA-256, reenumeración antes de consolidar, exclusiones explícitas, gaps y unidades pendientes impiden cierre completo; API/manifiesto legacy sin inventario conservan cola como `UNVERIFIED`. Añadir CLI inventory y matriz de partición, sin afirmar lectura o profundidad semántica. Rechazar raíces solapadas, IDs de ciclo inseguros y archivos duplicados. Documentar límite de manifiesto 2 MiB y protocolo de ejecución separado del destino de ciclo.
- Diez regresiones nuevas de cobertura y expectativas legacy corregidas; revisión independiente detectó incompatibilidad de inicio del ciclo y bypass léxico de raíces con `//`, corregidos con protocolo separado y normalización después del rechazo de symlinks. Suite seleccionada: 48 tests Python aprobados con runtime; excluido el test dependiente de lanzadores personales. Carga nativa de las ocho skills aprobada sin modelos. Pruebas con entorno AppImage saneado; evidencias externas.
- Reconciliar progreso con recibos: nueve cierres Syncify agrupan 73 hallazgos, con QA parcialmente documental; seis reparaciones RehabWeb con QA original y pruebas acotadas, reauditoría semántica posterior pendiente. Corregir requests declaradas: 73 y 218 en resúmenes distintos, incluyendo denegaciones y sin coste comparable. No acreditar cola completa, integración conjunta ni autonomía por estos resultados. Reflejar la cuota de mensajes por lanzamiento ampliada en el commit de canal precedente.
- Memoria/medición completa, evidencia humana y profundidad dual siguen siendo contratos de revisión, no servicios Host implementados; recomendaciones posteriores se conservan en informe externo, sin aplicarlas en esta unidad.

## Recuperación durable sobre fixtures y presupuesto durable — 2026-09-12

- `scripts/budget.py`: contrato local mínimo de límites durables (intentos/coste/tiempo) como ledger de eventos inmutables en estado externo: creación exclusiva, digest, reserva conservadora antes del trabajo, límites fijados una sola vez (reapertura distinta o alterada falla cerrada) y `BudgetExhausted` sin escritura. No mide procesos reales ni concede autoridad.
- Regresión `tests/test_recovery_durable.py` (7 tests): operación continuada de 4 unidades de cola fixture en una sola sesión con presupuesto persistente y agotamiento fail-closed; reinicio del controlador en durante QA / antes de publicar / después de publicar-antes de ack con reconciliación idempotente (cero escritores duplicados, cero integración repetida, candidato conservado, presupuesto sin reinicio, rechazo de reenvío ciego); caída de worker SIGKILL con reanudación; cancelación que termina los descendientes locales (evidencia por flock); timeout de turno de `run_check` que mata el grupo y deja RETAINED recuperable; reinicio del Host vía `host_launcher` en los tres puntos con estado host-side preservado, `/state` nueva por lanzamiento, sandbox sin visibilidad de recibos ni escritura del producto y QA invalidada por cambio de candidato.
- Límites documentados: el controlador fixture demuestra el contrato de reconciliación, no un Host real; descendientes remotos fuera de la capacidad aceptada; sin concurrencia hostil ni garantía ante pérdida de energía; sin QA semántica ni autonomía LLM. Suite completa: 38 tests Python aprobados con runtime instalado.

## Payload configurable y partes de assistant en el canal de inferencia — 2026-09-12

- `scripts/inference_channel.py`: payload por request configurable por lanzamiento (`payload_limit`, 1 MiB por defecto, tope duro 8 MiB) en lugar de la constante fija de 64 KiB que hacía morir los turnos de ~16 pasos (RETAINED F6-DUPLICATE-CONVERSATION-500); el tope se impone en las tres capas del lanzamiento y el launcher pasa el valor al receptor interno en argv como entero no secreto. Allowlist de assistant ampliada al formato real del runtime instalado: campos string `reasoning`/`reasoning_content`/`reasoning_text` y contenido como lista no vacía de partes exactas `{type:'text',text}`. Endpoint, modelo, autorización host-side, presupuesto de requests, cuotas de tokens/mensajes y el resto de la allowlist sin cambios; `reasoning_details` y formas malformadas siguen rechazadas.
- Regresiones nuevas en `tests/test_inference_channel.py`: payload >64 KiB aceptado con el default y rechazado con tope rebajado o sobre el tope duro, validación del argumento, campos/partes de razonamiento aceptados, diez formas malformadas rechazadas y camino real por launcher (payload grande 200; tope rebajado 400 sin upstream). Suite completa: 31 tests Python aprobados con runtime instalado.

## Canal de sesión multi-request de inferencia — 2026-09-12

- `scripts/inference_channel.py` amplía el canal de una request a una sesión acotada por lanzamiento, sin proxy general: presupuesto de requests configurable al construir el canal (12 por defecto, tope duro 256), cuota por request de hasta 32768 tokens (default del hijo, antes 32) y 64 mensajes (antes 8); los topes solo pueden rebajarse por lanzamiento. Endpoint, modelo, autorización host-side y allowlist de claves sin cambios.
- Agotado el presupuesto: error explícito fail-closed (503 en el canal, línea `FAIL CLOSED` en el log externo) y canal cortado por el resto del lanzamiento; requests posteriores sin upstream. Además, el broker aparta su capa de texto de stdout para que el corte de pipes no degrade el cierre del intérprete (antes exit 120 por flush fallido).
- Regresiones nuevas: multi-request dentro de presupuesto, corte por agotamiento sin upstream, cuotas nuevas y rebajadas por lanzamiento, validación fail-closed de argumentos de cuota y camino real por launcher con presupuesto 1 (503, 502 y `FAIL CLOSED` con un solo hit upstream). Suite completa: 29 tests Python aprobados con runtime instalado.
- Sonda real en Host aislado (presets externos, sesión `nrouter-raw/Orquestrador`): turno completo de subagente con herramientas sobre `nrouter-raw/Subagents-Audits` completó con 2 requests por el canal (segunda pierna con `tool_calls` y resultado `tool`), max_tokens 32768 del hijo aceptado sin overrides, presupuesto 12 gasto 2, ningún payload denegado y denegación de ruta no autorizada intacta. Evidencia en `/tmp/inference-multi-request/probe-auditor.json`.

## Extensión del canal para turnos de subagentes — 2026-09-12

- Allowlist del broker de inferencia ampliada de forma mínima y fail-closed a las claves estructurales de turno que emite el runtime (`tools`, `tool_choice`, `tool_calls`/`tool_call_id` en mensajes); endpoint, modelo y autorización siguen fijos host-side y toda clave o forma no listada se rechaza sin alcanzar el upstream.
- Regresión nueva: turno con `tools` permitido y reenviado, payload con clave no listada rechazado; suite completa 28 tests Python aprobados.
- En Host aislado con la sesión `nrouter-raw/Orquestrador`, un turno completo de subagente con `tools` completó por el canal sobre la ruta autorizada. Los turnos multi-request siguen limitados por el presupuesto de una request por lanzamiento y las cuotas de tokens/mensajes, registradas como pendiente exacto.

## Corrección de mapeo de sesión a canal RAW — 2026-09-12

- Fila de sesión/orquestador de las composiciones externas corregida a canal RAW: `nrouter-raw/Orquestrador` en `auditor-preset` y `repair-preset`; QA `nrouter-raw/Subagents-Audits` y ejecución `nrouter/Subagents-Coding` (NORMAL) sin cambios. Orquestrador verificado en el catálogo RAW no secreto.
- Re-aceptación aislada por preset con host_launcher: sesión con modelo efectivo `nrouter-raw/Orquestrador`, proyección de política exacta, skills con cuerpo exacto y denegación fail-closed de rutas no listadas; ninguna ruta no autorizada alcanzó el broker.
- Humo mínimo de la ruta corregida: `nrouter-raw/Orquestrador` respondió `OK` (`text-delta`, `finish=stop`); el `EMPTY_RESPONSE` previo no se reprodujo en el canal RAW. Regresión de mapeo intacta (usa rutas fixture, no nrouter).

## Presets externos del flujo y mapeo de modelos — 2026-09-12

- Compuestos presets externos de Auditoría y Reparación en el workspace (`workflow-presets`) sin tocar `~/.dsh`, presets distribuidos ni routing global; delegación copiada de Standard con `modelSelectionSettings: true` y skills nativas por workspace, sin declarar proveedores ni modelos.
- Verificados el proveedor NORMAL `nrouter` y el RAW `nrouter-raw` por catálogo no secreto y humo aislado: orquestador `nrouter/Orquestrador`, QA `nrouter-raw/Subagents-Audits` y ejecución `nrouter/Subagents-Coding` respondieron `OK`; el `EMPTY_RESPONSE` previo de Orquestrador no se reprodujo.
- Aceptación aislada por preset: sesión por preset, modelo efectivo de sesión, proyección de política exacta al mapeo, skills con cuerpo exacto y denegación fail-closed de rutas no listadas. Límite material documentado: el broker de humo niega el turno completo del hijo (`tools` fuera de la allowlist del canal).
- Límite del runtime comprobado: `allowedModels` es ajuste global único del Host; un preset que intenta su propio namespace de selección falla el montaje, sin fallback silencioso. Regresión nueva `tests/test_dsh_preset_mapping.py`; suite completa 27 tests Python aprobados.

## Hito 1: launcher Host externo — 2026-09-12

- Añadida envolvente Linux/bubblewrap reusable con lecturas explícitas, estado externo nuevo, namespaces privados y fallo cerrado; sin entorno heredado, instalación ni cambios de runtime/modelos.
- Una regresión permanente con servicios DSH reales y fixtures externos verifica lecturas/escrituras autorizadas, denegaciones aun con policy permisiva, descendientes, secretos/sockets ocultos y rechazo sin fallback. Suite: 23 tests Python y check Node aprobados.
- Composición web completa arrancada con listener privado: el 401 inicial era autenticación esperada. Cliente con secreto exclusivamente desechable obtuvo HTTP 200/HTML, creó sesión Standard y cargó ambos modos con `ctx.tools.execute` sobre su agente real; proveedor/origen/cuerpos exactos comprobados, sin modelos ni credenciales activas.
- Conservado cwd original con bind explícito RO y padres vacíos; `/tmp` privado mediante bind, sin remapeo por symlink. Misma regresión extendida: cwd Node/bash exacto, lectura relativa, denegación de escritura original y secreto hermano oculto. 23 tests Python y Node aprobados; Host autenticado repetido. No acredita conducta LLM, QA ni autonomía; acceso acotado a red/proveedor queda pendiente.

## Diagnóstico de inferencia aislada — 2026-09-12

- La selección vigente `nrouter/Orquestrador` terminó `EMPTY_RESPONSE` con `responseModel=muse-spark-1.3-contributor-free` y sin `text-delta`; se clasificó como fallo de contenido/modelo upstream, no como fallo QA ni del broker.
- Sin tocar routing persistente, una selección temporal explícita ya declarada por Host (`nrouter/ag/gemini-3.8-flash-high`) devolvió `OK`, `text-delta`, `finish=stop` y `responseModel=gemini-3.8-flash` mediante el launcher aislado. La unidad Syncify completa permanece pendiente.

## Evidencia externa Syncify/RehabWeb — 2026-09-12

- Syncify completó 73 reparaciones externas con recibos `ACCEPTED`; 15 hallazgos permanecen retenidos por decisión humana.
- RehabWeb completó su propia auditoría `rehabweb-audit-001` sobre 6 unidades y 381 archivos, con cola externa independiente.
- Corregido el launcher operativo externo para aislar el estado por `dshHome` y parametrizar el nombre del proyecto; no se modificó DSH ni sus plugins.
- La reparación de RehabWeb queda pendiente de recibo final; ambos productos permanecen sin cambios.

## Auditoría completa y ciclo circular — 2026-09-11

- Añadidos contratos stdlib para capabilities externas reutilizables y ciclos de auditoría con partición, deduplicación, DAG y archivo compacto.
- Añadida la skill `workflow-complete-auditor` para auditoría completa por unidades, cola externa de reparación y reauditoría circular.
- Reparación continua consume la cola vigente sin pedir el siguiente hallazgo; permisos y capacidades no se autoconceden.
- El piloto real de Syncify queda como criterio externo de aceptación, sin convertir sus artefactos en contenido versionado.

## Integridad de sesiones programadas — 2026-09-10

- Exigir `started.json` inmediato en un directorio externo nuevo, creación autónoma de fixtures/prerequisitos y paths absolutos, sin depender del scheduler o contexto implícito.
- Exigir `checkpoint.json` y `report.md` siempre, con `RETAINED` ante bloqueo o prerequisito ausente, y `finish.json` como cierre referenciado; nunca sobrescribir artefactos previos.
- La regresión se aplica al protocolo documental externo; no se añadió código porque el framework no ejecuta ni administra estas sesiones programadas.

## Corrección tras revisión 3 — 2026-09-10

- Rechazar payloads anidados no objeto de evidencia/tareas genéricas antes de persistir COMPLETE, consistente con el consumidor; comprobar ausencia de cierre y recuperación por registros corregidos o PARTIAL.
- Tres revisiones independientes realizadas: 5 / 3 / 1 hallazgos encontrados y corregidos, además de las seis correcciones originales. Esta corrección no constituye una cuarta revisión.
- Suite final: 17 tests Python y regresión Node nativa aprobados, sin instalación ni modelos. Reproducciones 2/3 originales se detienen en rechazos corregidos; no se declara QA real ni autonomía de producto.

## Correcciones de revisión 2 — 2026-09-10

- Impedir colisiones de ciclo entre lotes solapados reservando el componente final de los IDs ordinarios.
- Mantener cuota de 16 con reservas de cierre y etapas reconstruidas en toda publicación; PARTIAL libera etapas, COMPLETE las conserva. Documentar política conservadora.
- Validar IDs y enlaces anidados antes de conjuntos/mapas; regresiones dirigidas y ciclo positivo al límite de cuota. 16 tests Python aprobados; sin QA semántica ni garantías Host nuevas.

## Correcciones de revisión 1 — 2026-09-10

- Validar check opcional de audit y rechazar JSON no objeto sin traceback de AttributeError.
- Reservar sufijos de ciclo, limitar lotes a 53 caracteres y validar el esquema COMPLETE al consumir handoff.
- Añadir regresiones dirigidas; 13 tests Python aprobados. Autopruebas de corrección, no revisión independiente 2.

## Integridad del ciclo local — 2026-09-10

- Corregir handoff COMPLETE/OPEN, escrituras poscierre, temporales ajenos y resolución de enlaces.
- Ligar etapas positivas a evidencia de misión hashada y `verify`; reauditoría comparte sus prerrequisitos. Auditor distinto también del ejecutor.
- Reforzar ciclo sintético con artefactos reales del fixture y entrega COMPLETE; no acredita QA real ni concurrencia hostil.

## Preparación de prueba completa — 2026-09-10

- Añadir `docs/trial-readiness.md` como checklist compacto de gates, evidencia, paradas y salida para Auditor/Reparación continua.
- Añadir `tests/test_two_mode_cycle.py` con onboarding externo, auditoría, reparación roja→verde, QA fixture, reauditoría mecánica, entrega y handoff, sin modificar producto.
- Reforzar `missions.py reaudit` para exigir check íntegro y hashes de salida en reparaciones aceptadas.
- Mantener los límites: QA fixture no es QA independiente real; no se acredita Host, sandbox, recuperación, IPC Tauri, integración ni autonomía.

## Mapa técnico de roles — 2026-09-10

- Añadir `bind_role()` para declarar bindings locales `executor`/`qa`/`auditor` y rechazar reasignaciones incompatibles.
- Mantener el binding como control declarativo aislado: la propiedad de lote sigue siendo de un caller local y la autenticidad/autoridad Host multi-actor permanece pendiente.

## Identidad declarada por etapa — 2026-09-10

- Añadir `actor_id` a los estados executor/QA/auditor y rechazar el mismo actor para QA y auditor respecto de la etapa anterior.
- Mantener la diferenciación como control mecánico declarado, no como prueba de independencia estadística o autenticidad fuerte.

## Estados locales de ciclo — 2026-09-10

- Añadir estados mecánicos `executor`, `qa` y `auditor` a lotes completos.
- Requerir candidato antes de QA y QA `VERIFIED` antes de `ACCEPTED`; conservar `RETAINED` cuando QA queda `UNVERIFIED`.
- Mantener la etapa 4 como `PARCIAL`: los estados no acreditan independencia real, autorización Host ni continuidad autónoma.

## Integridad e inmutabilidad de cierres — 2026-09-10

- Hacer idempotente el cierre de lote y rechazar conflictos de cierre.
- Exigir que cada tarea de una entrega completa enlace evidencia del mismo lote.
- Validar hashes y existencia de todos los registros referenciados al resolver un handoff completo.
- Mantener la etapa 4 como `PARCIAL`; no implementar recuperación ni autorización Host.

## Entrega local multi-registro — 2026-09-10

- Añadir apertura de lote, registros `evidence`/`task` y cierre `COMPLETE`/`PARTIAL` con referencias hashadas, owner, gaps y validación de entrega.
- Verificar entrega completa, parcial, owner incorrecto y cierre incompleto en el fixture local.
- Mantener la etapa 4 como `PARCIAL`; no implementar todavía roles Host, continuación ni recuperación durable.

## Handoff local mínimo — 2026-09-10

- Añadir emisión y resolución validada de `INICIO_LOTE: {"receipt_id":"..."}` sobre el publicador local.
- Verificar formato exacto, ID inexistente, corrupción, recibo no entregable y resolución desde otro proceso.
- Mantener la etapa 4 como `PARCIAL`; no implementar todavía handoff Host, roles ni entrega multi-registro.

## Robustez del publicador local — 2026-09-10

- Añadir límites de recibo y cantidad de registros, escritura mediante temporal exclusivo y enlace sin sobrescritura, y validación reforzada al resolver.
- Mantener etapa 2 como `PARCIAL`: no se afirma durabilidad ante crash/pérdida de energía ni publicación Host.

## Primitive local de publicación — 2026-09-10

- Añadir `scripts/publisher.py` y su regresión para publicación/resolución externa, IDs opacos, identidad/autorización suministradas, límites, idempotencia, conflictos y detección de corrupción.
- Reclasificar la etapa 2 como `PARCIAL`; el módulo no es publicador Host, sandbox, autenticación fuerte ni prueba de durabilidad ante crash.

## Reconciliación del plan arquitectónico — 2026-09-10

- Conservar el plan original archivado como arquitectura de destino completa, sin presentarlo como implementación terminada.
- Añadir `PLAN_IMPLEMENTACION.md` como índice compacto de progreso por etapas; los detalles históricos y la evidencia de ejecución permanecen fuera de este repositorio.
- Reclasificar publicador Host, handoff automático, flujo habitual, recuperación, integración y transferencia como capacidades futuras o parcialmente ensayadas, según evidencia disponible.
- Mantener v0.1 como operación acotada con recibos locales, controles mecánicos y reauditoría mecánica; no acreditar autonomía LLM, IPC Tauri nativo, sandbox OS, durabilidad ni QA semántica por documentación o hashes.

## Separación H1-only de QueueItem — 2026-09-10

- Preparar fuera del repositorio una unidad nueva que retira únicamente `service`, `quality`, `effective_service`, `original_service` y `allow_fallback` en `ui/src/api/types.ts`; no aceptar la expansión completa previa.
- Conservar reproducción roja y prueba verde, `change_scope` explícito de un archivo y reauditoría mecánica de hashes/alcance.
- Mantener `RETAINED`/`UNVERIFIED` por falta de QA independiente real observable; no modificar ni integrar Syncify.

## Cierre honesto del contrato v0.1 — 2026-09-10

- Añadir `missions.py reaudit` para ligar mecánicamente candidato, prueba y resultado antes de la revisión semántica.
- Extender el ciclo sintético con la reauditoría incremental; se conserva explícitamente la revisión semántica para Auditor/QA.
- v0.1 se declara operativa acotada, no autonomía ni piloto real de producto.

## Alcance de Reparación continua verificado — 2026-09-10

- Trayectoria Standard sintética cargó `workflow-continuous-repair` y `workflow-bounded-acceptance`.
- Una prueba verde con archivo fuera de `change_scope` fue rechazada por `missions.py verify`; `RETAINED` se conservó.
- No se modificó producto/framework y no se afirma QA semántica multimodelo.

## Alcance explícito de reparación — 2026-09-10

- Exigir `change_scope` en tareas repair y rechazar aceptación si cualquier archivo fuera de ese subconjunto difiere de `base`, aunque la prueba pase.
- Añadir regresiones para alcance ausente y archivo inspeccionado modificado fuera de permiso.


## Descubrimiento nativo desde el padre — 2026-09-10

- Conservar cwd padre en Standard mediante enlaces individuales gestionados a las copias externas; manifiesto, dry-run, conflictos sin sobrescritura y retirada solo de entradas propias. Sin configuración global ni edición del consumidor/producto.
- Regresión DSH instalada: dos padres, un scope compartido con las filas reales de skills de Standard, cuerpos y destinos exactos, rechazo cruzado y retorno al primer agente. No Host completo, modelos ni garantía de sandbox.
- Separar errores de argumentos bash de denegaciones; no escalada automática a acceso total. Validación nativa de emparejamiento/rechazo y escenarios conductuales documentados, no enforcement nuevo.
- Siete tests Python aprobados; guía de preparación integrada y límites de permisos explícitos.

## Operación acotada v0.1 — 2026-09-10

- Añadir entradas Auditor y Reparación continua en Standard, despacho START y guía con permisos efectivos del producto hermano; sin producto vivo, presets nuevos ni autonomía Host.
- Añadir recibos task/result, runner argv explícito con timeout/salidas/digests y verificación documental de candidato/prueba/referencia QA; no autentica revisión semántica ni autoridad.
- Copiar skills completas recursivamente; repetición idéntica y actualización explícita respaldada, conservando conflictos y ediciones locales.
- Seis regresiones Python aprobadas, incluido ciclo sintético rojo/verde y rechazos negativos; QA fixture declaradamente simulada. Carga nativa determinista de siete skills con DSH instalado, sin modelos. Piloto real pendiente.

## Aceptación acotada en Standard — 2026-09-10

- Registrar carga nativa y aplicación observadas en tres turnos de un caso sintético: ACCEPTABLE → RETAINED → ACCEPTABLE, sin ampliar requisitos ni escribir archivos.
- Comprobar un cuarto turno con evidencia necesaria ausente: UNVERIFIED, solicitud ligada al candidato, sin ejecución ni ampliación de alcance.
- No modificar la skill: no se observó un defecto en este recorrido. Conservar límites de validación y trayectoria privada externa.

## Corrección de descubrimiento DSH

- Entrada por raíz del workspace externo; retirada plantilla inefectiva sobre proveedor global desactivado por Web. Sin overlay ni cambios globales.
- Regresión contra servicios instalados: alcance de agente, padre frente a workspace, carga nativa de cinco cuerpos y hashes sin modelos.
- Preparación rechaza enlaces en destino `.agents/skills` y manifiestos de origen; pruebas de no escritura fuera del workspace.

## Overlay portable para skills por proyecto — 2026-09-10

- Añadir `docs/dsh-project-profile.patch.yml` como plantilla de override con `customSkillDirs` y placeholder explícito.
- Mantener la ruta real fuera del repositorio; no aplicar ni modificar perfiles globales.
- Documentar que el override debe probarse en un perfil dedicado y que el preset efectivo puede montar el proveedor en alcance propio.

## Skills por proyecto: adaptador de loader documentado — 2026-09-10

- Documentar que la copia en `.agents/skills` no activa el proveedor en DSH.
- Registrar el fragmento conceptual `customSkillDirs`/`includeDefaultRoots` para un Host/preset dedicado, sin aplicarlo globalmente ni presentarlo como configuración universal.
- Mantener la activación efectiva pendiente de una sesión DSH reiniciada con overlay comprobado.

## Frontera canónica durante misiones — 2026-09-10

- Corregir START.md: una misión operativa no edita el framework canónico para adaptar su procedimiento ni pide hacerlo durante la misma misión.
- Añadir `framework_clean()` y regresión permanente para detectar cambios inesperados en la raíz Git del framework.
- Mantener las propuestas de evolución fuera del árbol hasta una misión de mantenimiento autorizada.

## START.md — punto de entrada legible por agentes — 2026-09-10

- Crear START.md: procedimiento de incorporación de proyecto con alcance, límites y retorno, todo consultable sin exigir al usuario un prompt largo.
- Actualizar README: instrucción breve de arranque DSH Standard y modelo de publicación commit→push→pull.
- Publicación por commit con push autorizado; el usuario jala cambios con pull en su clon de Syncify.

## Repositorio canónico — 2026-09-10

- Establecer reglas persistentes en AGENTS.md: solo archivos distribuibles y regresiones permanentes en Git; datos y resultados de ensayos fuera del árbol.
- Adoptar evaluación incremental de sesiones DSH Standard para mejorar el flujo; no cambia los dos modos finales.
- Configurar identidad Git autorizada para commits locales; sin publicación remota.

## Distribución inicial — 2026-09-09

- Separar framework reusable de archivos privados, clones, runtime y antecedentes; preservar originales en archivo hermano no publicable.
- Conservar arquitectura y sus invariantes, generalizar perfiles y mantener dos modos objetivo: Auditor y Reparación continua. Search no es dependencia.
- Añadir onboarding Python explícito, comprobación local y cinco skills portables; separar estado real de arquitectura.
- Preservar publicador experimental en archivo externo por sus restricciones de ensayo, sin anunciar adaptación universal ni autonomía completa.
- Preparar Git local sin remoto; commit pendiente de identidad configurada. No elegir licencia en nombre del titular.

Cambios futuros se registran aquí de forma breve y en commits; antecedentes privados no se importan al historial público.
