# Estado comprobado del framework

**Actualización:** 2026-09-27
**Arquitectura vigente:** [v3.0](../ARQUITECTURA_FLUJO_AGENTES.md) (norma implementada; lifecycle operativo EN CURSO/IMPLEMENTED_NOT_VERIFIED)
**Índice de progreso:** [C0–C7 y post-C7](../PLAN_IMPLEMENTACION.md)

Este documento registra únicamente el estado vigente. El detalle de iteraciones anteriores está en Git/`CHANGELOG.md`, no aquí.

## Base técnica comprobada

El repositorio conserva servicios Host y regresiones reutilizables:

- onboarding externo idempotente, manifest y enlaces gestionados;
- inventario/partición SHA-256 y cobertura fail-closed;
- contratos de misión, checks y verificación documental;
- publicador local idempotente y etapas de rol;
- presupuesto durable, decisiones y métricas append-only;
- controlador Host con locks/reconciliación/cancelación;
- launcher Linux aislado y canal de inferencia acotado;
- plugin de escritura con semántica de escalada corregida;
- QA, reauditoría semántica, archivo/restauración y crash de proceso/contenedor demostrados;
- distribución privada por red y clean-room del código base demostrada.

Estas capacidades constituyen la base MVP comprobada. No equivalen al flujo de incorporación 3.0 ni a modos finales para proyectos nuevos.

## Eliminaciones de vigencia

- No hay presets Auditor/Reparación genéricos en la distribución canónica.
- No hay skills operativas universales del MVP en el árbol actual.
- No hay planes P0–P9, M1–M8 ni diagramas v2.4 en la documentación vigente.
- Los nombres/configuraciones usados en proyectos de prueba no son defaults.
- El contrato Creator de dos archivos fue reemplazado por el paquete generacional completo.

El historial eliminado sigue disponible en Git y no debe reconstruirse como instrucciones actuales.

## Estrategia de skills aprobada

Creator selecciona primero la biblioteca base inmutable y el catálogo de patrones especializados; después compone o aplica overrides declarativos. Solo genera una extensión cuando demuestra que esas capas no aplican, con contrato, escenarios y aceptación específica. Una skill transferida no es válida automáticamente para otro proyecto. La regeneración no sustituye bases por conveniencia.

Las fuentes externas evaluadas quedan registradas con procedencia fijada en `library/source-registry.json` (esquema `source-registry.schema.json`): 43 fuentes — 20 repositorios de skills/índices/runtimes y 23 estándares o guías, con `fastapi-pydantic-docs` sustituida por `fastapi-framework` y `pydantic-framework` fijadas por observación directa — con URL canónica, commit, fecha, licencia, estado y decisión razonada. Una fuente sin revisión fijada o con licencia no resuelta no puede ser `CANDIDATE` ni `ACTIVE`; la adquisición es solo manual con pin, sin npx/marketplace/descargas, con staging fuera del árbol y validación Host previa. El inventario pormenorizado de 11.407 entradas que respalda las decisiones se mantiene en un espacio de auditoría externo; el registro solo conserva su digest SHA-256.

La biblioteca base está materializada en `library/library.json` con contenido y escenarios en `library/base/`. La conversión de la base está completa: 21 skills (reimplementación propia con atribución MIT de `obra-superpowers` y `addyosmani-agent-skills`) — brainstorming, writing-plans, executing-plans, systematic-debugging, test-driven-development, requesting-code-review, receiving-code-review, verification-before-completion, finishing-a-development-branch, spec-driven-development, constraint-driven-development, source-driven-development, security-and-hardening, context-engineering, api-and-interface-design, observability-and-instrumentation, documentation-and-adrs, performance-optimization, incremental-implementation, code-simplification y deprecation-and-migration. Cada skill base tiene un escenario positivo y al menos uno de veredicto FAIL/BLOCKED, y la cobertura es bidireccional y obligatoria en la suite. Se rechazaron como base idea-refine, interview-me y using-agent-skills por ser meta o interactivas sin valor universal.

El catálogo especializado contiene cuatro patrones activados por evidencia, con contenido en `library/catalog/` y escenarios propios: `fastapi-openapi-contract-check` (dominio `python-backend`, fuente `fastapi-framework` fijada por observación directa), `web-accessibility-wcag-audit` (dominio `web-frontend`, fuente `wcag-22` fijada por versión de especificación — 2.2, W3C Recommendation 2024-12-12 —), `http-security-headers-verifier` (dominio `web-platform`, fuente `mdn-web-docs` fijada por instantánea de mdn/content) y `aws-iam-policy-static-review` (dominio `aws-security`, fuente `aws-waf-apg` fijada por instantánea de awsdocs/iam-user-guide). Todos se activan solo ante señales observables declaradas en su contrato; los criterios de activación declarados deben aparecer verbatim en el contenido del patrón, y la regresión lo exige. Los estándares versionados se fijan mediante `spec_version` (esquema de registro y de biblioteca extendidos); el pin por commit queda reservado a repositorios. El catálogo no recibe más patrones sin evidencia de dominio y aceptación específica.

El despacho de Creator es automático desde `bootstrap install` y desde `creator_client.py`: se reutiliza una única instancia DSH Web sana o se inicia una sola desde el padre común, y se adquiere la sesión DSH local (cliente inyectado, `DSH_HOME` o casas estándar) y se supervisa la generación dentro del presupuesto; sin sesión autenticada el run queda `CREATED`/`PREPARED` recuperable con la acción concreta, y `--launch-dsh` permite arrancar `dsh web` explícitamente. La única sesión Creator se crea ligada al workspace del run (`workspace/create` + `workspaceId`), sin sesiones evaluator/reviewer ni delegación. Creator produce exactamente dos presets de usuario; el Host prepara `<Proyecto>-workspace/mode-state`, materializa un bundle de declaraciones `@deepseek-ai/dsh-agent-preset`, lo instala mediante `pluginManager/installBundle` y exige confirmación real de `agentPresets/list`. La aceptación previa es determinista (`READY_FOR_INSTALL`) y no afirma evaluación dinámica; `ACTIVE` solo sigue a publicación y roster verificados. El lanzamiento aplica el overlay `cordis-patch.yml` (`dsh web --patch`) que carga `workflow_write` con el resolver de sandbox corregido, y el prompt versionado prohíbe todo uso de `sandbox_permissions`/`justification` y releva esa prohibición a cada subagente delegado. Nunca se descarga ni instala DSH por iniciativa del framework.

La selección de Creator está integrada con la biblioteca: `bootstrap install` congela un snapshot validado de la biblioteca en el run, el prompt versionado de Creator lista las skills base y los patrones de catálogo con sus criterios de activación, los contratos que reutilizan `base-library` o `specialized-catalog` deben declarar `reuse_reference` con la entrada exacta, y el validador Host resuelve esas referencias contra el snapshot del run. La activación transaccional exige un veredicto Host ACTIVE explícito y la identidad de base se deriva por el mismo método en `install` y `update`.

## Experiencia final objetivo

```text
usuario configura DSH/proveedor una vez
→ bootstrap install
→ Creator descubre/diseña/genera modos y skills específicos
→ Creator invoca accept
→ Host valida y respalda
→ aceptación automática
→ activación transaccional o rollback
→ usuario opera <Proyecto>-auditor y <Proyecto>-continuous-repair
```

Esta experiencia está implementada (C0–C7) y en hardening sobre piloto real; el detalle vigente del despacho está en la arquitectura §7-B3 y el uso en [usage.md](usage.md).

## Límites vigentes

- `THIRD_PARTY_NOTICES.md` incorporado para atribución MIT de jsmastery-pro/skills.
- Publicación remota y release público requieren autorización del titular según la política de distribución.
- La pérdida física de energía y descendientes remotos hostiles no tienen garantía total.
- Configurar proveedor en DSH es responsabilidad previa del usuario; el framework no obtiene API keys.
- El hardening de piloto requiere evidencia real: un prompt o un estado declarativo no acreditan autonomía, carga de skills ni aislamiento.

## C0–C7 — completadas

| Etapa | Estado | Salida requerida |
|---|---|---|
| C0 | HECHO | schemas/fixtures/manifests/contracts/tests/handoffs/drift y procedencia |
| C1 | HECHO | `bootstrap install` determinista y reanudable |
| C2 | HECHO | sesión DSH Creator real (preset cordis) generó paquete específico y llamó accept |
| C3 | HECHO | validador Host fail-closed de 10 capas verificado sobre paquete real C2 (READY_FOR_ACCEPTANCE) |
| C4 | HECHO | backups verificados, staging, swap atómico y rollback comprobados sobre paquete real |
| C5 | HECHO | Creator invocó accept; Host ejecutó validación estática, ledger de evidencia y veredicto |
| C6 | HECHO | pilotos clean-room ejecutados en proyecto Python y proyecto multiparte con DSH real |
| C7 | HECHO | reconciliación de runs, THIRD_PARTY_NOTICES.md (MIT) y promoción verificada |

## Hardening posterior a C7 (piloto real)

Unidades incorporadas tras C7, guiadas por evidencia de sesiones DSH reales; el detalle y las regresiones de cada una están en `CHANGELOG.md`:

| Unidad | Estado | Contenido comprobado |
|---|---|---|
| Registro de fuentes y biblioteca materializada | HECHO | 43 fuentes con procedencia fijada; 21 skills base inmutables y 4 patrones de catálogo con escenarios y regresión bidireccional |
| Integración biblioteca ↔ Creator | HECHO | snapshot de biblioteca por run, prompt con base/catálogo y criterios de activación, `reuse_reference` resuelto por el validador Host contra el snapshot |
| Despacho automático y ciclo de vida DSH | HECHO | detección/parada de instancias previas, propiedad del puerto 3080 sin matar procesos ajenos, cookie HMAC del home, `npx -y` no interactivo con salida capturada y tokens redactados, resolutor de proveedor utilizable (aviso, no bloqueo; `DSH_PROVIDER_STRICT=1` para parada dura) |
| Sesión ligada al workspace del run | HECHO | `workspace/create` + `session/create` con `workspaceId`; única sesión Creator, agrupada en la UI, frontera `workspace-write` en el workspace entero, sin sesiones evaluator/reviewer ni delegación |
| Política anti-escalada de sandbox | HECHO | el overlay del framework retira `sandbox_permissions`/`justification` de schemas y rechaza cualquier aparición residual antes de aprobación; los dos modos generados declaran el contrato exacto en lifecycle/persona first-party y su fuente monta `./anti-escalation.mjs`. La publicación reescribe solo esa fila a la ruta absoluta del guard copiado al bundle —el registro DSH vigente resuelve `config.plugins` desde `cordis.patch.yml`— y `agentPresets/read` verifica esa identidad efectiva; una regresión con el runtime DSH real monta la composición exacta de siete filas, comprueba bash ordinario y bloquea `workspace-write`/`danger-full-access` antes de aprobación |
| Transacción con veredicto Host | HECHO | `install` exige `host-verdict.json` ACTIVE ligado a la misma generación antes de activar |
| Aceptación Host aislada del Creator | HECHO | harness de aceptación del Host con evaluador y revisor aislados, casos ocultos con predicados privados, cardinalidad completa exigida y actores correlacionados con turnos reales de DSH; aceptación previa determinista (`READY_FOR_INSTALL`), sin afirmación de evaluación dinámica |
| Instalación de modos como presets DSH | HECHO | modos con `mode.json`/`preset.yml`/`agent.cordis.yml`/`SKILL.md`; Creator recibe del run los basenames reales case-sensitive de producto/workspace y la ruta exacta de `mode-state`, y el Host contrasta esa identidad estructurada antes de aceptar/instalar; instala un bundle `@deepseek-ai/dsh-agent-preset`, exige `application=applied`, roster sano y composición/raíz candidatas vía `agentPresets/read`; una actualización `restart-required` queda recuperable hasta relanzar DSH y repetir `bootstrap install` |
| Gate operativo y skills bundle-local | HECHO | composiciones fail-closed con las seis filas operativas, `dsh-tool-fs-search` configurado con `sampleOverCapGlobResults: false` y sin delegación/workflow/web/plugin-manager; frontmatter mínimo de modos/skills; copia completa y segura a `bundle/skills`, `includeDefaultRoots: false`, root absoluto del bundle y ambos IDs en recibo |
| Handoff durable y candidato automático | HECHO | contrato/bootstrap/persona first-party con anti-escalada exacta (`escalation_channel: forbidden`, argumentos prohibidos para todos los valores y denegación/error schema → RETAINED sin retry), schemas/caps, preflight/migración conservadora, archivo transaccional por digest de evidencia inesperada y originales esperados incompatibles (source path/motivo/digest; 8 MiB/archivo y 32 MiB totales), proyección estricta solo de registros válidos o mapeos inequívocos, candidato digest y límites de commit implementados con regresiones. La reanudación sucia usa `resume_policy: exact-recorded-only`: antes de provisionar lee el `candidate` estricto de `work-items.json` y solo acepta el target determinista exactamente registrado con estado `DIRTY` o `RETAINED` pendiente de verificación, mismo path/branch/base/digest de hallazgos, identidad worktree y HEAD base, canonical limpio e inalterado, diff candidato no vacío con digest y lista completa de paths coincidentes, confinados a archivos regulares sin symlinks ni submódulos. Un comando central separado valida la reanudación sin exigir candidata limpia ni cambiar bytes; registro ausente o discrepante conserva la colisión `RETAINED` y nunca adopta un worktree sucio arbitrario. Antes de editar, Repair registra la candidata como `PROVISIONED` (`record_before_first_edit: true`, `record_statuses: [PROVISIONED, DIRTY]`); si ese registro no se persiste no cambia código y queda `RETAINED`, y tras el primer cambio lo actualiza a `DIRTY` con digest y paths del diff. Una candidata registrada que aparezca sucia por un turno interrumpido se recupera con ese mismo comando de registro, nunca creando otra ni descartando el diff; un target sucio sin registro sigue sin adoptarse (`unrecorded_dirty_target: RETAINED-never-adopted`). Si el registro coincide exactamente y solo su digest de diff quedó obsoleto, `stale_record_policy: reconcile-then-resume` recalcula la identidad desde la base y los IDs reales, re-mide el diff de esa candidata probada y reanuda sin intervención del operador; una discrepancia real de path, branch, base o hallazgos permanece `RETAINED`. Regresiones cubren dos turnos, rechazo de digest/path/base/status o registro ausente, rutas inseguras e invariancia canónica. El startup exige primera bash sin override (workdir omitido o `.`) y un `first_bash_command` exacto centralizado que empieza por `set -eu`, imprime `pwd`, valida basename/producto/workspace en un único `test` y solo entonces emite `__IMPROVEMENT_LAYOUT_OK__`; lifecycle y persona exigen ese `success_sentinel` exacto para continuar y retienen ante su ausencia o resultado no disponible, sin exigir marcador de exit code 0 porque DSH lo omite en éxitos. El cwd esperado es el basename del padre común real de producto/workspace. Auditor conserva candidata previa, incluido `INTEGRATED`, que solo Host/operador puede registrar. Lifecycle/persona lo fijan estructuralmente sin incrustar ruta absoluta del mantenedor. El Auditor declara además `bash_workdir: session-cwd-only-all-calls`: toda bash omite workdir o usa `.`, reescribe antes de invocar comandos para apuntar al producto mediante `git -C`/`npm --prefix`/`cargo --manifest-path` o equivalente, y cualquier override accidental retiene inmediatamente; Repair provisiona desde el cwd de sesión con workdir omitido y comando central exacto: calcula el destino absoluto con `$PWD`, crea el worktree hermano mediante `git -C ./<producto>` y verifica realpath/registro; después usa como workdir exactamente el nombre candidato relativo al cwd de sesión, nunca `.` ni una ruta anidada bajo producto. Schema, validador y persona exigen esos campos y `unrelated_candidates: ignore-preserve`; el preflight central comprueba solo invariantes canónicos y path/branch target, reutiliza únicamente esa identidad exacta y no bloquea ni altera worktrees ajenos clean, dirty o stale. Regresiones ejecutan el comando en repos temporales, prueban sibling/HEAD/rama/registro/limpieza canónica, reutilización exacta, preservación de múltiples candidatas ajenas y rechazo de colisiones del target. El reclamo y la reanudación tienen ya prueba DSH real: un turno de Repair persistió `PROVISIONED` antes de editar, re-registró `DIRTY` tras el primer cambio y volvió a registrarlo con digest nuevo tras ampliar la reparación, sin colisiones ni intervención del operador, y el operador integró solo con commit, fast-forward y push. Quedan como límites declarados que bash conserva alcance de escritura del padre y la actualización multiarchivo ordinaria no tiene CAS/lease: no se afirma aislamiento ni atomicidad concurrente. El mecanismo se ejercitó con DSH real en tres campañas (RehabWeb, LoboApp y el self-test del framework); lo que no se afirma son esos dos límites, no el contrato |
| Piloto tardis (Syncify) | HECHO | cada salida del piloto se convirtió en cambio de flujo y regresión. Syncify cerró el ciclo con 77 hallazgos persistidos y atendidos por los modos, integración solo por commit/fast-forward/push del operador y CI verde (Rust + frontend + Python) en `b9413eb`; el registro de cierre declara D-01..D-04 como alcance condicionado, no como trabajo pendiente: SoundCloud/Apple Music dependen de credenciales del propietario. La auditoría encontró además que el registro de `candidate` que escribe un modo generado puede no cumplir el esquema (forma propia en vez de la del contrato), con lo que el preflight lo archivaría en silencio; esa unidad de endurecimiento es G1 y está cerrada |
| Instalación limpia de principio a fin | HECHO | entorno sin contamination (clon nuevo de Improvement y de RehabWeb, home de DSH nuevo con solo credenciales y modelos, roster inicial de cuatro presets de fábrica) y un único `bootstrap.py install --project … --launch-dsh` que produce `Host: ACTIVE` con `rehabweb-auditor` y `rehabweb-continuous-repair`; después un prompt simple de auditoría persistió 45 hallazgos con handoff y un prompt de seis palabras reparó dos CRITICAL en una candidata hermana, con el producto intacto hasta que el operador integró |
| Preparación de lanzamiento público | HECHO | G1–G3, re-anclaje de base y G7 (verificación contra el stack real, sin stubs) implementados y en suite verde (743 pruebas): el `recording_command` y el `reconcile_command` emiten el objeto JSON exacto a persistir verbatim (ruta relativa, head en base) —causa raíz del patrón RehabWeb de candidatas con campos extra o ruta absoluta—, la persona prohíbe añadir/cambiar campos, el preflight devuelve un informe que nombra lo que descarta y la instalación lo incluye en su resultado; `decisions.py` y `metrics.py` dejan de ser huérfanos y se cablean al cierre de turno del controlador Host (evento `turn` en `metrics/`, decisión ratificada en `decisions/`, fail-closed con unidad reconciliable); el estado activo gana `overflows.jsonl` como recibo de desbordamiento (caso Syncify 50/50 handoffs). G7 secerró además con la campaña de LoboApp: el plan nombra la capacidad por la ruta con la que puede invocarse (un `flutter test` desnudo era un `BLOCKED` injusto) y distingue «puede correr» de «esta sesión puede escribir en ella», pidiendo materializar con `cp -al` un SDK que se reescribe a sí mismo bajo `<workspace>/.stack/<stack>/` (17.659 ficheros, 0 bytes de disco). G0 quedó cerrada el 2026-09-30 con licencia Apache-2.0 elegida por el titular y `LICENSE` en la raíz, G5 el mismo día con README, quickstart no técnico y política de feedback, y G6 con el tag `v0.1.0-beta` publicado bajo autorización del titular; plan en [docs/plans/10-lanzamiento-publico.md](plans/10-lanzamiento-publico.md) |
| Recuento y reconciliación del estado gestionado | HECHO | `persisted_count` dejó de ser una afirmación del modo: un `count_command` central recalcula desde `findings.jsonl` los hallazgos `OPEN` de la base declarada, exige que el handoff los cubra exactamente (rechazo mecánico en `workflow_write` antes de escribir, con `persist_order` declarado) e imprime el número que se reporta. `PARTIAL` se decide como veredicto derivado, no como valor de enum: un registro por entrypoint con PASS/FAIL/BLOCKED y peor resultado ganando, y contradicciones PASS/FAIL rechazadas. `scripts/state_reconcile.py` y `bootstrap.py state` reconcilian el estado con el repositorio: cabeza integrada que una reescritura de historia borró (con `--repoint` acotado y recibo en `overflows.jsonl`), hallazgos `OPEN` con work item `VERIFIED` y hallazgos que ningún handoff tomó; `--retire` retira worktree y rama solo con todas las condiciones probadas y es idempotente |
| Ancla de evidencia del hallazgo | HECHO | `evidence.path` + `evidence.excerpt` con `line`/`located` calculados por la herramienta antes del write-intent: el fragmento ausente o ambiguo rechaza la escritura en vez de resolverse, y un hallazgo sin localización posible se persiste sin ancla, visible en `anchors`. El campo es opcional en el schema para no archivar la evidencia histórica: un registro antiguo de cinco campos sigue siendo válido. Técnica tomada de `alibaba/open-code-review` (`internal/diff/resolver.go`) y registrada en `library/source-registry.json` con el pin `a758d9c`; el diseño de RSI de `microsoft/skillopt` queda registrado como `CANDIDATE` sin adoptar su motor |
| Gate de holdout para la biblioteca de skills | IMPLEMENTED_NOT_VERIFIED | `scripts/corpus_compiler.py` compila los 55 escenarios de `library/` en casos ejecutables deterministas ligados por `corpus_digest`, y el oráculo se deriva en el Host: el caso público lleva `task`, fixture y `evaluated_claim`, nunca el veredicto esperado. `bootstrap.py bound-skill-gate` puntúa observaciones **ligadas** a corpus, candidato y versión de compilador; `bootstrap.py skill-gate-commit-check` exige un informe aceptado cuando cambia el corpus y trata `abstain` como bloqueo, no como permiso. Probado con las cuatro decisiones contra el corpus real. **Sigue sin verificarse contra un modo:** producir observaciones exige un proveedor que configura el operador, así que ningún cambio de biblioteca ha pasado aún por el gate con evidencia de un agente real. Confinamiento mecánico del auditor, medido aparte |

### `stack_coverage`: qué stack está probado y cuál está solo declarado

Once stacks declaran cómo verificarse. **Un comando escrito a mano no es cobertura**, y la
diferencia tiene que verse antes de que alguien confíe en él sobre su repositorio.
`tests/test_stack_coverage.py` pone una toolchain real en el `PATH` de cada stack y exige que
el plan nombre un comando que la shell puede invocar; luego la quita y exige que el plan nombre
la capacidad que falta en vez de asumir disponibilidad. Eso convierte "declarado" en
"resuelve o bloquea honestamente", que es lo comprobable sin un proyecto de cada tecnología.

| stack | comando declarado | evidencia de campaña real |
|---|---|---|
| `rust` | `cargo test`, `cargo clippy -- -D warnings` | **PROBADA** — Syncify (Rust/Tauri/Vue), CI verde en 3 jobs |
| `python-django` | `python manage.py test`, `django check` | **PROBADA** — RehabWeb, 108 pruebas Django reales |
| `python-generic` | `pytest -q`, `compileall` | **PROBADA** — el propio framework sobre sí mismo |
| `dart-flutter` | `flutter test`, `flutter analyze` | **PROBADA** — LoboApp, 166 pruebas Flutter |
| `node` | `npm test`, `npm run build` | declarada; resolución comprobada, sin campaña |
| `go` | `go test ./...`, `go vet ./...` | declarada; resolución comprobada, sin campaña |
| `java-maven` | `mvn -q test` | declarada; resolución comprobada, sin campaña |
| `java-gradle` | `./gradlew test` | declarada; resolución comprobada, sin campaña |
| `dotnet` | `dotnet test` | declarada; resolución comprobada, sin campaña |
| `php-composer` | `vendor/bin/phpunit` | declarada; resolución comprobada, sin campaña |
| `ruby` | `bundle exec rspec` | declarada; resolución comprobada, sin campaña |

Las siete sin campaña son el hueco real de la beta: si tu proyecto usa una de ellas, el plan
resuelve el comando y el framework no se inventa un `PASS`, pero nadie ha corrido todavía una
suite real de esa tecnología contra este flujo. Es exactamente lo que la beta sirve para
descubrir, y por eso se pide compartir el `mode-state` cuando la stack no esté en la tabla de
probadas.

**Meta vigente:** beta pública — cualquier persona con su repo y su DSH configurado instala
con un comando, opera los dos modos con prompts simples y reporta compartiendo su
`mode-state`. Las puertas G0–G6 del plan de lanzamiento son la definición operativa de
«terminado» para esa meta, y **las siete están cerradas**: G6 se completó el 2026-09-30 con
el tag `v0.1.0-beta` publicado bajo autorización del titular.

**Trabajo abierto: ninguno en la matriz de `PLAN_IMPLEMENTACION.md`.** D1, D2, D11 y F5
cerraron el 2026-10-01, junto con E1–E5. Lo que queda no es una fila abierta sino **evidencia que
sólo el operador puede producir**, y conviene nombrarla para que no se confunda con trabajo hecho:

- **El gate de biblioteca todavía no ha puntuado observaciones de un agente real.** El
  ejecutor existe (`bootstrap.py skill-gate-run`), el corpus es ejecutable y el gate decide, pero
  correrlo exige una sesión DSH con proveedor configurado. Sin ella el ejecutor **se abstiene
  nombrando lo que falta**, que es lo correcto y no un resultado.
- **El confinamiento mecánico está medido y aplicado como contrato, no comprovado en una
  campaña.** `tests/test_auditor_confinement.py` lo prueba contra el runtime real con `EROFS`;
  que un proyecto real lo ejerza bajo el flujo completo es lo que la beta comprueba.
- **Siete stacks están declarados y ninguno tiene campaña** (Node, Go, Maven, Gradle, .NET, PHP,
  Ruby). La tabla `stack_coverage` de arriba dice cuáles sí.

**D11: el corpus ya es ejecutable, y lo que falta es ejecutarlo contra un modo.** Los 55
escenarios de `library/` eran tablas de aserciones declarativas (`contract_declared: true`),
no tareas que un agente pudiera recibir. `scripts/corpus_compiler.py` les da forma
ejecutable determinista reutilizando `acceptance_harness._public_input`, y el oráculo se
deriva en el Host en vez de viajar en el caso público. La puerta que falta es ejecutar:
producir observaciones exige un proveedor que configura el operador, y el framework no lo
instala ni lo invoca. Hasta que eso ocurra, **ningún cambio de biblioteca ha pasado por el
gate con evidencia de un agente real**, y así queda dicho.

**D2: el auditor se puede confinar en el núcleo; el reparador no, y ya se sabe por qué.**
Contra `0.1.7-rc.2` instalado, la raíz escribible de `workspace-write` es el cwd de sesión,
y el producto es hermano del workspace **dentro** de ese cwd: la bash lo clobberaba de
verdad. Apuntar la política al workspace en vez de a la raíz de sesión lo corrige —el
producto queda fuera de `writableRoots()`, la bash recibe `EROFS` real y el auditor **sigue
pudiendo persistir sus hallazgos**—, que es lo que se creía imposible. El reparador sigue
bloqueado por una razón medida: `writableRoots()` admite **una sola** raíz configurable y el
reparador necesita dos, su candidata y el estado compartido; además `git worktree add`
registra el worktree en el `.git` del producto, que en una sesión confinada es de solo
lectura. Cerrarlo exige que el Host aprovisione la candidata fuera de la sesión confinada.
Todo está fijado en `tests/test_auditor_confinement.py` contra el runtime real.

**E6: la memoria se escribía y nadie la leía.** La auditoría de cierre de este
ronda encontró que `episodes.py` escribía `episodes.jsonl` y `episodes-index.json`
con diecisiete regresiones que probaban que el registro funciona, y que ningún camino
de producto leía el índice: la documentación decía «el auditor lo consulta antes de
persistir un hallazgo» y era cierto de una frase y falso del framework. `workflow_write`
calculaba la firma exacta con la que la memoria se indexa y la descartaba. Todas las
pruebas de aquel día eran verdaderas; ninguna era sobre lo que la unidadservía para.
Ahora la consulta ocurre en la misma escritura que el ancla: si la firma está en el
índice, el registro lleva `evidence.prior_episode` con la unidad que lo cerró y el
arreglo que funcionó, y `bootstrap.py state` cuenta esas repeticiones en `repeats`
porque una prevención que falló es un defecto distinto del primero. El hueco no se
tapó con una frase: se tapó con una regresión de ocho casos canario-comprobada, y con
otra que ata persona, contrato y plugin para que no vuelvan a divergir sin que nada
falle.

Suite de regresión: ver último registro en `CHANGELOG.md`; la suite completa corre en verde antes de cada cierre de unidad.
