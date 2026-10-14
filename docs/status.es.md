# Estado comprobado del framework · [English canonical](status.md)

**Actualización:** 2026-10-14
**Arquitectura vigente:** [v3.0](../ARQUITECTURA_FLUJO_AGENTES.md) (C0–C7 completadas; campaña U6 implementada en parte, sin aceptación operativa; lifecycle EN CURSO/IMPLEMENTED_NOT_VERIFIED)
**Índice de progreso:** [C0–C7 y post-C7](../PLAN_IMPLEMENTACION.md) · [vista de una página de todos los hitos](progreso-agentico.md)

Este documento registra únicamente el estado vigente. El detalle de iteraciones anteriores está en Git/`CHANGELOG.md`, no aquí.

**Aceptación al 2026-10-14:** la suite local pasa 1106 pruebas (11 omitidas). La verificación Host del implementador liga un comando al plan de capacidades verificado por digest; la detección de pila ya no confunde un proyecto Python con solo `requirements.txt` con Django. Un checkout fresco de Syncify remoto en `9e4cb5b` pasó seis pruebas del producto, pero el ensayo inicial de candidata encontró ese defecto de detección —ahora corregido— y no se obtuvo una nueva aceptación DSH del implementador. El preflight Host del corpus comprueba publicación ACTIVE, recibo y archivos de skills, pero se abstiene antes de crear sesión porque aún no puede acreditar el layout del preset por caso ni la carga efectiva de skills. El gate U6 bloquea un ledger sin identidad de candidata, pero no se obtuvo un nuevo journal U6 con veredicto Host. Un intento Creator post-budget terminó por HTTP 403/402 del proveedor antes de inferencia (cero tokens): no generó manifest y quedó RETAINED. Son gates de aceptación operativa abiertos, no una terminación de producción.

**Implementador (parcial, aceptación en un solo caso real):** el contrato Host/Creator admite un tercer preset `implementer` opcional y conserva las generaciones de dos roles; la transacción prueba publicación local de los tres. `mode_lifecycle.provision_implementation` liga petición exacta y base limpia a una sombra aislada en workspace, conserva el trabajo sucio al reanudar y `verify_implementation` mide diff y corre un caso de comportamiento en candidata (ahora liga el comando pedido a un plan de capacidades Host verificado por digest y bloquea entrypoints ausentes, alterados o no disponibles); regresiones focalizadas lo ejercitan con producto temporal externo, pero este cambio no tiene aceptación nueva en un turno DSH real. **El 2026-10-10 un turno DSH real** sobre un producto ficticio dejó una candidata externa con commit `95aa9b2`, 6/6 tests nuevos correctos y el producto sin el campo pedido, sin commit/merge/push implícitos: el mecanismo se ejerció, en un solo caso y con la candidata creada como clon dentro del workspace. `skill_router` solo selecciona sobre roster cuya definición/entrypoint/bundle/recibo están ligados al manifest de la generación ACTIVE; abstiene si falta evidencia, presupuesto o integridad. **Sí se cargaron e invocaron skills en sesión DSH real** (auditor 3, reparador 2, implementador 1; un turno trivial no cargó ninguna), pero `skill_router` sigue siendo solo selector informativo y no se ha ejercitado contra una sesión real. **La reparación ya no pide un `worktree` del producto**: `mode_lifecycle.provision_repair` crea, desde el Host, un repositorio sombra con `.git` propio bajo el workspace y la sesión solo lo verifica y registra (contrato `Host-provision_repair-shadow-only`). **Probado en dos ensayos externos distintos, con límite bien acotado**: bajo headless DSH real (`x1-live`) la sombra del Host, `PROVISIONED → DIRTY`, el diff verificado, tests 3/3 y la reanudación exacta se ejercieron, con producto intacto; bajo web RPC con preset real y `bwrap` (`x1-preset-real`) el preset se resolvió, cargó su skill y ejecutó los sentinelas, pero el supervisor detuvo los turnos por presupuesto **antes de editar** (99.022 medidos con 128.213 proyectados, y después 97.973 con 127.227, frente a 120.000 por turno; el ensayo acumuló 243.165 totalTokens); **El 2026-10-11, con el techo subido a 200.000, el modo completó la edición y luego el cierre**: 11 pasos y 180.107 tokens para reparar (`Math.round(valor)` → `Math.round(valor * 100) / 100` y el total con IVA redondeado sobre la tarifa ya redondeada), con el producto canónico intacto. En un turno posterior, **ya con los comandos publicados como archivos verificados por digest**, el modo cerró el ciclo: emitió `__IMPROVEMENT_CANDIDATE_RECORD__` con `status: DIRTY`, `candidate_diff_digest` y `changed_paths`, lo persiguió en `work-items.json` y ejecutó el entrypoint del producto contra la sombra (3/3 en verde). El ciclo íntegro bajo preset real queda **probado en sus dos tramos**, con la salvedad de que el registro `DIRTY` lo persistió el modo mediante edición sobre el archivo de estado, no por el comando de registro canónico. Sigue sin probarse confinamiento mecánico de bash en campaña. Workflow de usuario entra por `bootstrap workflow run`, no por plugin de modo; se mantiene la prohibición de filas delegat/subagent/workflow. No hay publicación remota.

**Integración y retiro de reparación:** la sombra del Host no comparte ancestry con el producto;
el operador obtiene y revisa un diff completo, incluyendo cambios sin commit, antes de decidir
si aplica un patch y verifica en el producto. `candidate_diff_command` registra identidad y rutas,
no entrega un patch listo para aplicar; `shadow_candidate.patch_digest` compara `shadow-base`
con `HEAD` y no cubre el trabajo sin commit. `state_reconcile.retire` verifica la identidad de worktrees del diseño anterior y de
sombras actuales, pero **ABSTAINED** antes de borrar cualquiera de los dos, incluso con
evidencia de integración: ni `git status` ni el recibo inventarían todo el contenido
desechable. La retirada de ambos queda como decisión manual del operador. Los pilotos previos que usaron worktree son historia, no instrucciones de
integración vigentes.

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

Las fuentes externas evaluadas quedan registradas con procedencia fijada en `library/source-registry.json` (esquema `source-registry.schema.json`): 50 fuentes — 27 repositorios de skills/índices/runtimes y 23 estándares o guías, con `fastapi-pydantic-docs` sustituida por `fastapi-framework` y `pydantic-framework` fijadas por observación directa — con URL canónica, commit, fecha, licencia, estado y decisión razonada. Una fuente sin revisión fijada o con licencia no resuelta no puede ser `CANDIDATE` ni `ACTIVE`; la adquisición es solo manual con pin, sin npx/marketplace/descargas, con staging fuera del árbol y validación Host previa. El inventario pormenorizado que respalda las decisiones se mantiene en un espacio de auditoría externo; el registro solo conserva su digest SHA-256. La superficie de descubrimiento de nuevas fuentes es la búsqueda `topic:claude-skills` de la API de GitHub, filtrada por hechos verificables (licencia, mantenimiento, pruebas) y con adopción solo por análisis por skill con pin manual; la frescura nunca ordena.

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

- `THIRD_PARTY_NOTICES.md` incorporado para atribución MIT de jsmastery-pro/skills, y ampliado a
  `obra/superpowers` y `addyosmani/agent-skills`, que son los upstreams que la propia biblioteca
  declara en cada `## Procedencia` y que hasta ahora no llegaban al aviso público (E20).
- Publicación remota y release público requieren autorización del titular según la política de distribución.
- La pérdida física de energía y descendientes remotos hostiles no tienen garantía total.
- Configurar proveedor en DSH es responsabilidad previa del usuario; el framework no obtiene API keys.
- El hardening de piloto requiere evidencia real: un prompt o un estado declarativo no acreditan autonomía, carga de skills ni aislamiento.

## Qué pruebas no se ejecutan aquí

La cuenta que se publica («NNN pruebas en verde») no es el total, y decirlo es
justo lo que la hace publicable. La cifra vigente se **mide**, no se recuerda:
`PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp python3 -B -m unittest discover -s tests`
cerró el 2026-10-14 con `Ran 1106 tests … OK (skipped=11)` en este
árbol de trabajo. Esta corrida local no constituye aceptación operativa DSH.
**Once regresiones se saltan** en una máquina
sin los componentes externos, y todas nombran el componente que falta:

| componente ausente | qué se pierde |
|---|---|
| `DSH_MODULE_ROOT` con runtime instalado | las 7 de confinamiento del auditor (`tests/test_auditor_confinement.py`, `EROFS` real contra bwrap), el arranque real de servicios (`tests/test_host_launcher.py`) y la escalada same-mode del plugin |
| `node` en `PATH` | las regresiones que conducen el módulo del plugin directamente |
| `bubblewrap` | la recuperación durable de proceso/contenedor |
| `jsonschema` | la paridad de `acceptance-plan` con su JSON Schema (la validación pura en Python sigue corriendo) |

Ninguna es un skip incondicional, y una regresión que se salta sin nombrar un
componente que el repositorio no distribuye ya no puede existir:
`tests/test_architecture_consistency.py` lo comprueba sobre el texto de cada
`skipTest`.


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
| Registro de fuentes y biblioteca materializada | HECHO | 50 fuentes con procedencia fijada; 21 skills base inmutables y 4 patrones de catálogo con escenarios y regresión bidireccional |
| Integración biblioteca ↔ Creator | HECHO | snapshot de biblioteca por run, prompt con base/catálogo y criterios de activación, `reuse_reference` resuelto por el validador Host contra el snapshot |
| Despacho automático y ciclo de vida DSH | HECHO | detección/parada de instancias previas, propiedad del puerto 3080 sin matar procesos ajenos, cookie HMAC del home, `npx -y` no interactivo con salida capturada y tokens redactados, resolutor de proveedor utilizable (aviso, no bloqueo; `DSH_PROVIDER_STRICT=1` para parada dura) |
| Sesión ligada al workspace del run | HECHO | `workspace/create` + `session/create` con `workspaceId`; única sesión Creator, agrupada en la UI, frontera `workspace-write` en el workspace entero, sin sesiones evaluator/reviewer ni delegación |
| Política anti-escalada de sandbox | HECHO | el overlay del framework retira `sandbox_permissions`/`justification` de schemas y rechaza cualquier aparición residual antes de aprobación; los dos modos generados declaran el contrato exacto en lifecycle/persona first-party y su fuente monta `./anti-escalation.mjs`. La publicación reescribe solo esa fila a la ruta absoluta del guard copiado al bundle —el registro DSH vigente resuelve `config.plugins` desde `cordis.patch.yml`— y `agentPresets/read` verifica esa identidad efectiva; una regresión con el runtime DSH real monta la composición exacta de siete filas, comprueba bash ordinario y bloquea `workspace-write`/`danger-full-access` antes de aprobación |
| Transacción con veredicto Host | HECHO | `install` exige `host-verdict.json` ACTIVE ligado a la misma generación antes de activar |
| Aceptación Host aislada del Creator | HECHO | harness de aceptación del Host con evaluador y revisor aislados, casos ocultos con predicados privados, cardinalidad completa exigida y actores correlacionados con turnos reales de DSH; aceptación previa determinista (`READY_FOR_INSTALL`), sin afirmación de evaluación dinámica |
| Instalación de modos como presets DSH | HECHO | modos con `mode.json`/`preset.yml`/`agent.cordis.yml`/`SKILL.md`; Creator recibe del run los basenames reales case-sensitive de producto/workspace y la ruta exacta de `mode-state`, y el Host contrasta esa identidad estructurada antes de aceptar/instalar; instala un bundle `@deepseek-ai/dsh-agent-preset`, exige `application=applied`, roster sano y composición/raíz candidatas vía `agentPresets/read`; una actualización `restart-required` queda recuperable hasta relanzar DSH y repetir `bootstrap install` |
| Gate operativo y skills bundle-local | HECHO | composiciones fail-closed con las seis filas operativas, `dsh-tool-fs-search` configurado con `sampleOverCapGlobResults: false` y sin delegación/workflow/web/plugin-manager; frontmatter mínimo de modos/skills; copia completa y segura a `bundle/skills`, `includeDefaultRoots: false`, root absoluto del bundle y ambos IDs en recibo |
| Handoff durable y candidato automático | HECHO (contrato; ciclo íntegro con preset real EJERCITADO EN DOS TURNOS) | Anti-escalada exacta (denegación/error schema → `RETAINED` sin retry), preflight y recibos durables. `mode_lifecycle.provision_repair` provisiona desde el Host una sombra con `.git` propio y recibo en `<workspace>/candidates/repair-<digest16>`; el modo verifica esa identidad, registra `PROVISIONED` antes de editar y `DIRTY` después, con digest de contenido y lista de rutas regulares. Reanuda solo la candidata exactamente registrada (`resume_policy: exact-recorded-only`); base o producto cambiados, colisión, symlink, recibo ausente o identidad discrepante retienen sin adoptar ni borrar trabajo ajeno. El auditor conserva el handoff y no escribe el producto. X1 headless DSH real probó `PROVISIONED → DIRTY`, diff, tests 3/3 y reanudación con producto intacto; X1 con preset web real cargó la skill y los sentinelas y, en la tanda de techo 120.000, los tres turnos se detuvieron por presupuesto antes de editar (243.165 `totalTokens` acumulados; 97.973 medidos con 127.227 proyectados en el último; solo skill, layout y provisión costaron 48.694). Con techo 200.000 el turno llegó a editar (180.107 medidos, 11 pasos) y un turno posterior cerró el ciclo: el modo registró `DIRTY` con digest y rutas, persistió `work-items.json` y ejecutó el entrypoint (3/3). Los tests los ejecutó el modo contra la sombra, no el operador. Las tres campañas previas que creaban worktrees del producto e integraban por fast-forward son historia, no el procedimiento actual. El operador integra el patch revisado, sin merge de rama sombra; `state_reconcile.retire` no borra sombras: ABSTAINED ante ellas, incluso con evidencia exacta de integración. No se afirma aislamiento mecánico ni CAS/lease multiarchivo a partir del contrato. |
| Piloto tardis (Syncify) | HECHO | cada salida del piloto se convirtió en cambio de flujo y regresión. Syncify cerró el ciclo con 77 hallazgos persistidos y atendidos por los modos, integración solo por commit/fast-forward/push del operador y CI verde (Rust + frontend + Python) en `b9413eb`; el registro de cierre declara D-01..D-04 como alcance condicionado, no como trabajo pendiente: SoundCloud/Apple Music dependen de credenciales del propietario. La auditoría encontró además que el registro de `candidate` que escribe un modo generado puede no cumplir el esquema (forma propia en vez de la del contrato), con lo que el preflight lo archivaría en silencio; esa unidad de endurecimiento es G1 y está cerrada |
| Instalación limpia de principio a fin | HECHO | entorno sin contamination (clon nuevo de Improvement y de RehabWeb, home de DSH nuevo con solo credenciales y modelos, roster inicial de cuatro presets de fábrica) y un único `bootstrap.py install --project … --launch-dsh` que produce `Host: ACTIVE` con `rehabweb-auditor` y `rehabweb-continuous-repair`; después un prompt simple de auditoría persistió 45 hallazgos con handoff y un prompt de seis palabras reparó dos CRITICAL en una candidata hermana, con el producto intacto hasta que el operador integró |
| Preparación de lanzamiento público | HECHO | G1–G3, re-anclaje de base y G7 (verificación contra el stack real, sin stubs) implementados y en suite verde (743 pruebas): el `recording_command` y el `reconcile_command` emiten el objeto JSON exacto a persistir verbatim (ruta relativa, head en base) —causa raíz del patrón RehabWeb de candidatas con campos extra o ruta absoluta—, la persona prohíbe añadir/cambiar campos, el preflight devuelve un informe que nombra lo que descarta y la instalación lo incluye en su resultado; `decisions.py` y `metrics.py` dejan de ser huérfanos y se cablean al cierre de turno del controlador Host (evento `turn` en `metrics/`, decisión ratificada en `decisions/`, fail-closed con unidad reconciliable); el estado activo gana `overflows.jsonl` como recibo de desbordamiento (caso Syncify 50/50 handoffs). G7 secerró además con la campaña de LoboApp: el plan nombra la capacidad por la ruta con la que puede invocarse (un `flutter test` desnudo era un `BLOCKED` injusto) y distingue «puede correr» de «esta sesión puede escribir en ella», pidiendo materializar con `cp -al` un SDK que se reescribe a sí mismo bajo `<workspace>/.stack/<stack>/` (17.659 ficheros, 0 bytes de disco). G0 quedó cerrada el 2026-09-30 con licencia Apache-2.0 elegida por el titular y `LICENSE` en la raíz, G5 el mismo día con README, quickstart no técnico y política de feedback, y G6 con el tag `v0.1.0-beta` publicado bajo autorización del titular; plan en [docs/plans/10-lanzamiento-publico.md](plans/10-lanzamiento-publico.md) |
| Recuento y reconciliación del estado gestionado | HECHO | `persisted_count` dejó de ser una afirmación del modo: un `count_command` central recalcula desde `findings.jsonl` los hallazgos `OPEN` de la base declarada, exige que el handoff los cubra exactamente (rechazo mecánico en `workflow_write` antes de escribir, con `persist_order` declarado) e imprime el número que se reporta. `PARTIAL` se decide como veredicto derivado, no como valor de enum: un registro por entrypoint con PASS/FAIL/BLOCKED y peor resultado ganando, y contradicciones PASS/FAIL rechazadas. `scripts/state_reconcile.py` y `bootstrap.py state` reconcilian el estado con el repositorio: cabeza integrada que una reescritura de historia borró (con `--repoint` acotado y recibo en `overflows.jsonl`), hallazgos `OPEN` con work item `VERIFIED` y hallazgos que ningún handoff tomó; `--retire` comprueba la identidad e integración de un worktree `INTEGRATED` **del diseño anterior** pero se abstiene antes de borrar la rama o el worktree; también se abstiene ante la sombra actual sin ancestry, así que su retirada es revisión manual del operador |
| Ancla de evidencia del hallazgo | HECHO | `evidence.path` + `evidence.excerpt` con `line`/`located` calculados por la herramienta antes del write-intent: el fragmento ausente o ambiguo rechaza la escritura en vez de resolverse, y un hallazgo sin localización posible se persiste sin ancla, visible en `anchors`. El campo es opcional en el schema para no archivar la evidencia histórica: un registro antiguo de cinco campos sigue siendo válido. Técnica tomada de `alibaba/open-code-review` (`internal/diff/resolver.go`) y registrada en `library/source-registry.json` con el pin `a758d9c`; el diseño de RSI de `microsoft/skillopt` queda registrado como `CANDIDATE` sin adoptar su motor |
| Gate de holdout para la biblioteca de skills | IMPLEMENTED_NOT_VERIFIED | `scripts/corpus_compiler.py` compila los 55 escenarios de `library/` en casos ejecutables deterministas ligados por `corpus_digest`, y el oráculo se deriva en el Host: el caso público lleva `task`, fixture y `evaluated_claim`, nunca el veredicto esperado. `bootstrap.py bound-skill-gate` puntúa observaciones **ligadas** a corpus, candidato y versión de compilador; `bootstrap.py skill-gate-commit-check` exige un informe aceptado cuando cambia el corpus y trata `abstain` como bloqueo, no como permiso. Probado con las cuatro decisiones contra el corpus real. **Sigue sin verificarse contra un modo**, y la razón operativa ya no es solo el proveedor: `skill-gate-run` exige un adaptador evaluador Host que verifique antes de `session/create` el layout por caso y la skill efectiva de cada uno de los 25 objetivos; el CLI no lo ofrece, así que hoy abstiene (`scripts/skill_gate_run.py:604-608`). Los 55 casos son casos de 25 skills, no pruebas del modo auditor, y un intento real de SC-123 dio `NOT_COVERED` por targeting/layout, no por mejora medida. Confinamiento mecánico del auditor, medido aparte |

### Ejecutor de workflows en el Host (U1–U3) y campaña por defecto (U6)

Unidades U1–U3 del plan aprobado para `/workflow` sobre DSH; el detalle y las regresiones de cada una están en `CHANGELOG.md`. Lo implementado y probado para U1–U3 es Host puro, sin sesión DSH real — y así se declara:

- **U1 · ejecutor sin DSH.** `scripts/workflow.py` ejecuta planes JSON con pasos `gate`/`join`/`fase`: plan validado fail-closed (ids únicos, dependencias previas y acíclicas por construcción, tipos conocidos), run dir externo `<workspace>-workflow/<run_id>/` con modo 0700, y journal append-only con cadena de digest y punto de control atómico `head.json` (patrón `metrics.py`); la reanudación por replay salta solo un paso con `STEP_COMPLETED` verificado por digest, y `verify` re-verifica la cadena por replay y falla cerrado ante alteración, truncado o prolongado. Salidas como comando-decisión: `RUN_COMPLETED` (exit 0) y `RUN_RETAINED` con causa (exit 1).
- **U2 · entrada bootstrap y abstención.** `bootstrap.py workflow run|verify` con `--run-root` anulable y adquisición del cliente DSH por la vía no-launch (jamás lanza `dsh web`); ante un plan con paso `ask` sin cliente disponible **se abstiene**: nada hecho, nada escrito, sin run dir, nombrando la pieza que falta (exit 1).
- **U3 · paso `ask` probado con cliente falso.** Sesión DSH nueva por intento con el preset verificado del proyecto (`agentPresets/list` + composición operativa exacta incl. `./anti-escalation.mjs`), `request_id` determinista por (run, paso, intento), poll con quiescencia transitiva fail-closed, deadline con `cancel_session` + gracia y `RETAINED`, errores de transporte convertidos en `RETAINED` con causa, y reanudación [corr-3]: la sesión viva de un intento sin terminal recibe el mismo `request_id` o se re-observa su transcript; sesión perdida es `RETAINED`, nunca re-despacho a sesión nueva. Sin DSH real: las pruebas usan un cliente falso inyectado.

Regresiones de U1–U3: `tests/test_workflow_executor.py`, `tests/test_workflow_bootstrap.py` y `tests/test_workflow_ask.py`; sus recuentos anteriores (14, 5, 8) no incluyen las regresiones U6 añadidas a esos ficheros.

**U6 · plan de campaña por defecto (implementación, no aceptación).** `scripts/campaign_plan.py` genera bytes deterministas de plan v1, manifiesto con digest y prompts bajo `.dsh-managed/campaign/` después de publicar presets verificados; `rondas_max` vale 2 por defecto. `scripts/transaction.py` lo escribe tras activar/publicar presets y devuelve recibo; `RESTART_REQUIRED` solo deja `pendiente-de-activacion`, `NO_OP` materializa o conserva los bytes sin reescritura, y rollback restaura tanto `capability-plan.json` como el directorio de campaña. El plan por defecto no declara dependencias `join`: los ocho pasos se ejecutan en orden. Son pruebas del mecanismo, no una campaña real completada ni una aceptación de U6.

| Paso por defecto, en orden | Función y resultado documentable |
|---|---|
| `preflight` (gate) | Comprueba manifiesto, presets DSH y stacks: PASS (0) o BLOCKED (2); BLOCKED retiene el run, no acredita auditoría. |
| `auditar` (ask) | Usa preset auditor; produce `evidence/campana/auditoria.json` si completa; sin cliente/preset verificado hay ABSTAINED antes del run. |
| `verificar-pre` (gate) | Deriva del ledger del producto `evidence/veredicto.json`: PASS (0), FAIL (1) o BLOCKED (2). FAIL continúa como paso fallido, BLOCKED retiene. |
| `reparar-1` (ask) | Declara preset reparador condicionado a `FAIL` del gate previo; con FAIL hoy retiene sin despacharse (véase límite abajo); con PASS registra `ASK_SKIPPED`. Resultado contratado: `evidence/campana/reparar.json`. |
| `verificar-post` (gate) | Vuelve a derivar PASS/FAIL/BLOCKED del ledger; FAIL continúa, BLOCKED retiene. |
| `reparar-2` (ask) | Condicional a `FAIL` de `verificar-post`, con el mismo contrato; con FAIL hoy retiene, con PASS registra `ASK_SKIPPED`. |
| `verificar-final` (gate) | PASS/FAIL/BLOCKED desde el ledger; FAIL aborta y retiene, BLOCKED retiene. |
| `cerrar` (gate) | Solo emite PASS (0) sin leer el ledger; no acredita por sí mismo que las verificaciones anteriores hayan pasado. |

El `result_contract` de cada ask exige `path` y admite `evidence_name` (por defecto `.`); `if_veredicto` lee `evidence/veredicto.json` desde el gate anterior y emite `ASK_SKIPPED` si no coincide. La carga de resultados confina rutas/symlinks y aplica presupuestos (200 ficheros, 8 MiB por fichero, 256 MiB por raíz, JSON de resultado hasta 1 MiB): sobrepasarlos retiene. El preflight estático de joins rechaza en carga un registro mayor de 4096 B (50 dependencias aceptadas; 55 rechazadas en regresión). `scripts/campaign.py` solo lee el ledger `mode-state/verification-results.jsonl` del producto, **no lo escribe**: sin capacidad el valor es BLOCKED; con capacidad pero sin registros utilizables, FAIL. Los gates de verificación escriben BLOCKED como valor de `veredicto.json`, no existe evento `BLOCKED` propio del journal. El despacho FAIL→reparación **funciona**: un gate que sale 1 con `on_fail: continue` registra `STEP_FAILED` y queda en `failed_gates`, que `if_verdicto` acepta como fuente (`scripts/workflow.py:1547-1553`), así que el ask condicionado a su `FAIL` se despacha y el run acaba `RUN_COMPLETED` (regresión: `tests/test_workflow_ask.py:682-703`). Lo que no se ha probado es el ciclo completo con DSH real ni con el producto canónico.

**Canal System 1 (diseñado, no implementado).** El diseño del canal de modelos de decisión como propuesta advisory está en `docs/plans/system-one-decision-channel.md` y su prerequisito —envolver `session/selectModel` en el cliente— **ya está implementado y verificado** (`4352a55`): era el bloqueante que impedía ejercer el nivel de razonamiento por paso. Quedan por implementar la rúbrica versionada con digest y el piloto de deduplicación de hallazgos. Ninguna prueba afirma que un modelo de decisión haya decidido nada.

**Qué no existe aún:** aceptación de U6 ni corrida de campaña con DSH real. El sondeo en vivo anterior terminó en `plan ilegible` (sin run dir ni journal), no en PASS. Tampoco existen evento `BLOCKED` propio, `schema_version: 2`, `gate.cwd`, dos planes separados, escritura Host del ledger, `bootstrap campaign` ni clasificación universal de códigos; la integración con `acceptance.py` sigue siendo riesgo abierto. U4 (bundle) no se ejecutó y requiere autorización explícita; U5 (skill-doctrina en `library/`) no se ejecutó y requiere gate de biblioteca con sesión real del operador.

### Pase integral sobre DSH real (2026-10-10): qué se midió y qué no

El 2026-10-10 se ejecutó un ensayo con instalación real de `@deepseek-ai/dsh` `0.2.0-rc.2` (versión confirmada con `npm view`), un `DSH_HOME` de campaña aislado fuera del canónico y un producto **ficticio** con git real y un defecto conocido. Nada tocó el producto real del operador ni `~/.dsh`. Los artefactos viven fuera del repositorio canónico. El procedimiento verificado para reproducir la sesión quedó como skill permanente: `skills/dsh-maintenance-session/SKILL.md`.

**Comprobado en este pase, con comando y artefacto:**

| Comprobación | Resultado |
|---|---|
| Canal real de inferencia | `dsh --profile headless --json` con `DSH_HOME` aislado: `final.text = "PING-OK"`, `turn_end.reason.kind = completed`, `totalTokens = 6552`, exit 0 |
| Fixture ficticio en rojo | `FAILED (failures=1)` `70 != 30` antes de reparar |
| `bootstrap install` | run `CREATED`, run dir externo al canónico |
| Auditor real | 13 tool calls, `evidence/audit-finding.md` (2.030 B) con excerpt literal y salida de test |
| Reparador real | candidata externa `candidate-repair-ensayo-1`, commit `ab5c0c6`, diff `+1 -3`, tests PASS, producto intacto |
| Implementador real | candidata `candidate-implement-nivel`, commit `95aa9b2`, 6/6 tests nuevos OK, producto sin `nivel_alerta` |
| Workflow FAIL → reparación → PASS | run `r-5d7d11…` `RETAINED cause: gate-abort:gate-producto`; run `r-7761c0…` `COMPLETED` |
| Journals | `workflow.py verify` VERIFIED en ambos run dirs |
| Memoria de campaña | `MEMORY_RECONCILED {base 693ba47…, invalidated: 6, hits: 0, misses: 0}` |
| Skills en sesión real | auditor cargó 3, reparador 2, implementador 1; turno trivial → 0 tool calls |
| Abstención real | turno con `Decision: I abstain` verificado con write-probe, producto intacto |
| Validador Host | `READY_FOR_ACCEPTANCE`, 10/10 capas PASS sobre paquete real |
| Corpus gate antifraude | `action: reject` — candidato inventado pierde en partición de entrenamiento (0.488 < 1.000) |
| Confinamiento canónico | intento de escritura desde el repo canónico denegado; reintento con `danger-full-access` rechazado sin canal de aprobación |

**No probado (queda declarado, no se rellena con suposición):**

1. **`dsh web` sí arranca en esta máquina; arrancar el servidor nunca fue el hueco.**
   Comprobado el 2026-10-10 con la instalación real `@deepseek-ai/dsh` `0.2.0-rc.2` fuera del
   canónico: `dsh web --port 17999` imprimió `dsh web: http://127.0.0.1:17999/?token=…` y
   siguió sirviendo hasta el corte, con un `DSH_HOME` vacío. El pase del 2026-10-10 copió
   `profiles/web/` **con `node_modules/` vacío**, y ahí el servidor no levantó; ese fue el
   motivo real de aquella parada, no una carencia del producto. **Lo que sigue ausente es el
   adaptador evaluador Host por caso**: el despacho del corpus gate va por la API de sesión
   real (`session/create` + `session/prompt` + `session/page`) —no existe un endpoint
   `evaluator` en DSH 0.2.0-rc.2 (error de una revisión anterior,
   `scripts/skill_gate_run.py:64-83`, regresión en `tests/test_corpus_gate.py:623-631`)—, y
   antes de crear sesión el runner exige además que el adaptador verifique el cwd compatible
   por caso y la disponibilidad efectiva de cada skill objetivo; sin eso se abstiene
   fail-closed y sin gastar (`scripts/skill_gate_run.py:604-608`, regresión en
   `tests/test_skill_gate_run.py`). **El corpus tampoco es una prueba del modo auditor ni
   viceversa:** sus 55 casos apuntan a 25 skills concretas, y el modo que la ejecutaría es
   otro artefacto. Corolario medido del pase: el corpus gate
   (`bootstrap.py skill-gate-run`) se abstuvo fail-closed con
   `no hay sesión DSH utilizable: … No .credentials.yaml at <HOME>/.config/dsh`
   (`scripts/skill_gate_run.py:33-44`, `scripts/creator_client.py:1673-1690`). Conviene no
   confundir cuatro cosas distintas: que `dsh web` arranque (aquí sí, con home vacío), que
   exista un endpoint `evaluator` (no existe en 0.2.0-rc.2), que exista un adaptador Host que
   verifique layout y skill efectiva antes de `session/create` (tampoco: `ABSTAINED` sin
   gasto) y que el corpus compile una **skill** y no el **modo** que la despacharía. La
   cuarta es la causa medida de `NOT_COVERED` en el ensayo externo posterior
   (`corpus-fixed`): el caso `SC-123` apuntaba a la skill `source-driven-development` y el gate
   despachó al modo `fixture-auditor`, que además exigió el layout `<producto>/<workspace>` que
   el directorio del caso no tenía; el gate leyó solo `result.json`, que el modo no escribió, y
   se abstuvo fail-closed. Ni esa abstención ni aquella parada del home son un fallo del gate
   que computa: el gate de holdout ligado (`bound-skill-gate`) sigue decidiendo sobre
   observaciones reales y rechaza el `PASS` fabricado. Ver
   [progreso-agentico.md](progreso-agentico.md), filas X2/X3.
2. **Creator end-to-end no se probó en este pase.** Un turno headless real con el `creator-prompt.md` íntegro
   (29 tool calls, 734.064 tokens, cwd correcto) no persistió
   `generated/generation-manifest.json`; el run quedó `RETAINED`. El paquete que el validador
   Host aceptó en este pase lo produjeron las herramientas deterministas del framework a partir
   del contrato canónico, **no** el modelo. **Posteriormente, un ensayo externo sí generó con DSH real**
   (overlay headless model-facing, manifest `GENERATED` con 19 artefactos, `bootstrap accept` y
   Host → `ACTIVE`), pero esa prueba es **anterior** a la corrección de la contabilidad de
   presupuesto Creator por run, así que aquel `ACTIVE` no acredita generación
   post-presupuesto ni el gate vigente. Ver [progreso-agentico.md](progreso-agentico.md), fila X3.
3. **`git worktree add` quedó bloqueado por el sandbox de sesión.** `git -C <producto> worktree add
   -b <rama> <sibling>` falla con `fatal: cannot lock ref … Read-only file system` más
   `[sandbox: file access denied under workspace-write mode]`; el intento de escalar recibió
   `sandbox escalation to "danger-full-access" requires approval, but no approval channel is
   available`. Ese límite es el origen del cambio de diseño: la candidata **ya no es un
   worktree** sino un repositorio sombra con `.git` propio, provisionado por el Host, y la
   provisión de reparación queda implementada con `mode_lifecycle.provision_repair` +
   `shadow_candidate` (contrato `Host-provision_repair-shadow-only`,
   `schemas/modes.schema.json`), con regresión negativa en fixture `bwrap` de producto
   read-only y sombra escribible
   (`tests/test_mode_lifecycle.py:97-146`:
   `test_external_bwrap_read_only_product_writable_shadow_repair_session` y
   `test_host_repair_rejects_legacy_worktree_symlink_and_receipt_collision`).
   **Los comandos del ciclo ya no llevan el helper incrustado.** Empaquetar las utilidades
   (`candidate-diff.py`, `work-items-guard.py`, `finding-ids-digest.py`) como blob
   base64/base85 dentro del comando obligaba al modo a transcribir ~900 caracteres de alta
   entropía en cada llamada `bash`: un turno real de 200.000 tokens perdió el cierre del ciclo
   porque un solo `+` enviado en lugar de `>` en el payload provocó
   `zlib.error: incorrect data check` —con la reparación ya hecha y correcta—. Ahora el Host
   publica los tres archivos en `workspace/.dsh-managed/shared/`, el comando verifica su
   SHA-256 antes de ejecutarlos y el recibo de activación publica los tres digests bajo `published_helpers`; la
   publicación cubre todas las ramas, incluida la idempotente
   (`scripts/transaction.py:_publish_helper`, `scripts/mode_lifecycle.py:_helper_invocation`).
   **El ciclo íntegro bajo preset real quedó ejercitado en dos tramos.** Con techo de 120.000
   por turno, la tanda de `x1-preset-real` acumuló **243.165 totalTokens** y los dos últimos
   turnos se cortaron **antes de editar** (99.022 medidos con 128.213 proyectados, y 97.973 con
   127.227); solo cargar la skill, el layout y provisionar la sombra costó 48.694 tokens. Con el
   techo subido a 200.000 el turno **sí editó**: 11 pasos y 180.107 tokens facturables, la sombra
   quedó sucia con el defecto canónico reparado (`Math.round(valor)` → `Math.round(valor * 100) /
   100`, y el total con IVA redondeado sobre la tarifa ya redondeada) y el producto canónico
   quedó intacto. El turno paró por proyección (180.107 medidos frente a 208.828 proyectados)
   antes del cierre. En un turno posterior, y ya con los comandos publicados como archivos
   verificados por digest, el modo cerró el tramo que faltaba: emitió
   `__IMPROVEMENT_CANDIDATE_RECORD__` con `status: DIRTY`, `candidate_diff_digest` y
   `changed_paths`, lo persistió en `work-items.json` y ejecutó el entrypoint del producto contra
   la sombra con 3/3 en verde. Los tests que se ejecutaron inmediatamente después de la edición
   los corrió el operador desde fuera; los del turno de cierre los ejecutó el modo.
   **Coste de contexto medido; causa y techo suficiente aún no establecidos.** Medido sobre el
   journal del turno (`/tmp/x1journal/final.jsonl`), el contrato llega por tres canales en el
   contexto de cada paso: persona del preset (8.117 caracteres),
   cuerpo de la skill (24.635) y ciclo inyectado por el prompt del ensayo (17.961); suman
   50.713 caracteres en el contexto del primer paso, y los pasos posteriores releen contexto
   acumulado vía `cacheRead`. El solape textual es casi nulo —un fragmento de
   68 caracteres entre persona y skill, 0 esqueletos shell compartidos entre ciclo inyectado
   y skill— pero cada canal cumple un papel distinto (bootstrap, contrato y orden de ensayo). `cacheReadTokens` crece
   monótonamente (128 → 4.055 → 12.666 → 12.848 → 15.360) y el paso 2 costó 21.963
   `totalTokens` para un centinela de una línea. El techo de 200.000 ya se probó: alcanzó para
   editar y verificar, y lo que impidió cerrar dentro de ese mismo turno fue la proyección, no el
   techo.
   La parte previa a la carga de skill
   en `persona_prefix` (`scripts/mode_lifecycle.py:571-585`) es necesaria y no se recorta; la
   prosa operativa posterior se podrá recortar contra lo que ya garantiza el JSON del ciclo,
   cambiando la función canónica y las pruebas que fijan su texto exacto
   (`scripts/composition_contract.py:145-153`).

El presupuesto del Creator se mide **por run** y se evalúa antes de declarar éxito: los tokens
reales se pliegan por cada `seq` observada, el límite queda congelado con el deadline para que
una reanudación no lo relaje, y un turno final que cabe en reposo pero ya excedió el límite se
retiene en vez de aceptarse (`scripts/creator_client.py:_supervise_creator`,
`tests/test_creator_budget.py`). El ensayo X3 que dejó el Creator `ACTIVE` fue **anterior** a
esa corrección de contabilidad y no acredita el gate vigente. Los dos ensayos **X3
post-budget** quedaron `RETAINED` y ninguno llegó a `ACTIVE`: el primero se detuvo con
**1.127.176 totalTokens** frente a **1,25 M de presupuesto** dejando 122.824 de margen sin
gastar, y el segundo cruzó el techo con **1.270.969 totalTokens facturables** (1.009.664 de
ellos lecturas de caché, el 79 % de la factura). DSH cobra un paso de modelo de forma
indivisible, así que un observador del journal no puede parar exactamente en el techo: el
último paso fue el que lo pasó. En ambos el modelo seguía leyendo schemas sin manifest ni
`turn/end`. Cada cifra se recalculara aparte descomprimiendo el journal durable completo y
coincidió con la contabilidad en vivo.

Tampoco se midió coste en dinero en este entorno: se declara en tokens (≈1.456.519 tokens en los
seis turnos con uso medido). El pase es una muestra sobre un producto ficticio, no una campaña
sobre un repositorio real del operador.

### `stack_coverage`: qué stack está probado y cuál está solo declarado

Treinta stacks declaran cómo verificarse. **Un comando escrito a mano no es cobertura**, y la
diferencia tiene que verse antes de que alguien confíe en él sobre su repositorio.
`tests/test_stack_coverage.py` pone una toolchain real en el `PATH` de cada stack y exige que
el plan nombre un comando que la shell puede invocar; luego la quita y exige que el plan nombre
la capacidad que falta en vez de asumir disponibilidad. Eso convierte "declarado" en
"resuelve o bloquea honestamente", que es lo comprobable sin un proyecto de cada tecnología.

| stack | comando declarado | evidencia de campaña real |
|---|---|---|
| `rust` | `cargo test`, `cargo clippy -- -D warnings` | **PROBADA** — Syncify (Rust/Tauri/Vue), CI verde en 3 jobs |
| `python-django` | `python manage.py test`, `python -m django check` | **PROBADA** — RehabWeb, 108 pruebas Django reales |
| `python-generic` | `python -m pytest -q`, `python -m compileall -q .` | **PROBADA** — el propio framework sobre sí mismo |
| `dart-flutter` | `flutter test`, `flutter analyze` | **PROBADA** — LoboApp, 166 pruebas Flutter |
| `node` | `npm test`, `npm run build` | declarada; resolución comprobada, sin campaña |
| `go` | `go test ./...`, `go vet ./...` | declarada; resolución comprobada, sin campaña |
| `java-maven` | `mvn -q test` | declarada; resolución comprobada, sin campaña |
| `java-gradle` | `./gradlew test` | declarada; resolución comprobada, sin campaña |
| `dotnet` | `dotnet test` | declarada; resolución comprobada, sin campaña |
| `php-composer` | `vendor/bin/phpunit` | declarada; resolución comprobada, sin campaña |
| `ruby` | `bundle exec rspec` | declarada; resolución comprobada, sin campaña |
| `deno` | `deno test`, `deno lint` | declarada; resolución comprobada, sin campaña |
| `bun` | `bun test` | declarada; resolución comprobada, sin campaña |
| `android-gradle` | `./gradlew testDebugUnitTest`, `./gradlew lint` | declarada; resolución comprobada, sin campaña |
| `swift` | `swift test`, `swift build` | declarada; resolución comprobada, sin campaña |
| `cmake` | `ctest --test-dir build` | declarada; resolución comprobada, sin campaña |
| `meson` | `meson test` | declarada; resolución comprobada, sin campaña |
| `sbt` | `sbt test` | declarada; resolución comprobada, sin campaña |
| `elixir` | `mix test`, `mix format --check-formatted` | declarada; resolución comprobada, sin campaña |
| `erlang` | `rebar3 eunit`, `rebar3 xref` | declarada; resolución comprobada, sin campaña |
| `zig` | `zig build test`, `zig build` | declarada; resolución comprobada, sin campaña |
| `crystal` | `crystal spec` | declarada; resolución comprobada, sin campaña |
| `nim` | `nimble test`, `nimble build` | declarada; resolución comprobada, sin campaña |
| `julia` | `julia --project=. -e using Pkg; Pkg.test()` | declarada; resolución comprobada, sin campaña |
| `r` | `R CMD check --no-manual .` | declarada; resolución comprobada, sin campaña |
| `perl` | `prove -lr t` | declarada; resolución comprobada, sin campaña |
| `clojure` | `clojure -M:test` | declarada; resolución comprobada, sin campaña |
| `cabal` | `cabal test all` | declarada; resolución comprobada, sin campaña |
| `haskell-stack` | `stack test` | declarada; resolución comprobada, sin campaña |
| `dune` | `dune runtest`, `dune build` | declarada; resolución comprobada, sin campaña |

Las veintiséis sin campaña son el hueco real de la beta: si tu proyecto usa una de ellas, el plan
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
  correrlo exige, además de una sesión DSH con proveedor configurado, un **adaptador evaluador
  Host compatible** que verifique antes de `session/create` el layout por caso y la skill
  efectiva de cada uno de los 25 objetivos del corpus; el CLI no lo ofrece, así que hoy el
  comando se abstiene. Sin esas dos piezas el ejecutor **se abstiene nombrando lo que falta**,
  que es lo correcto y no un resultado.
- **El confinamiento mecánico está medido y aplicado como contrato, no comprovado en una
  campaña.** `tests/test_auditor_confinement.py` lo prueba contra el runtime real con `EROFS`;
  que un proyecto real lo ejerza bajo el flujo completo es lo que la beta comprueba.
- **Veintiséis stacks están declarados y ninguno tiene campaña**; la tabla `stack_coverage` de
  arriba los nombra todos.

**D11: el corpus ya es ejecutable, y lo que falta es ejecutarlo contra un modo.** Los 55
escenarios de `library/` eran tablas de aserciones declarativas (`contract_declared: true`),
no tareas que un agente pudiera recibir. `scripts/corpus_compiler.py` les da forma
ejecutable determinista reutilizando `acceptance_harness._public_input`, y el oráculo se
deriva en el Host en vez de viajar en el caso público. La puerta que falta es ejecutar:
producir observaciones exige un proveedor que configura el operador, y el framework no lo
instala ni lo invoca. Hasta que eso ocurra, **ningún cambio de biblioteca ha pasado por el
gate con evidencia de un agente real**, y así queda dicho.

**D2: el auditor se puede confinar en el núcleo; el worktree del reparador no.**
Contra `0.1.7-rc.2` instalado, la raíz escribible de `workspace-write` era el cwd de sesión,
y el producto hermano del workspace quedaba **dentro** de ese cwd: la bash lo clobberaba de
verdad. Apuntar la política al workspace en vez de a la raíz de sesión lo corrigió —el
producto queda fuera de `writableRoots()`, la bash recibe `EROFS` real y el auditor **sigue
pudiendo persistir sus hallazgos**—. En el diseño previo, el reparador estaba bloqueado:
`writableRoots()` admitía **una sola** raíz configurable y necesitaba dos, candidata y
estado compartido; además `git worktree add` registraba el worktree en el `.git` del
producto, que en una sesión confinada es de solo lectura. **Esa medida se confirmó el 2026-10-10 sobre DSH real**: `git -C <producto> worktree add -b <rama> <sibling>` devolvió `fatal: cannot lock ref … Read-only file system` más `[sandbox: file access denied under workspace-write mode]`, y las candidatas se crearon como `git clone --no-hardlinks` dentro del workspace, no como worktrees hermanos. Por eso el diseño ya no pide un worktree: `mode_lifecycle.provision_repair` (+ `shadow_candidate`) crea la candidata como **repositorio sombra con `.git` propio bajo el workspace, desde el Host**, con contrato `Host-provision_repair-shadow-only` y recibo de identidad; el modo solo lo verifica y lo registra. Pendiente: una corrida Creator íntegra que lo ejerza en sesión real.
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

**Segunda auditoría: la misma enfermedad, siete veces.** Una revisión sistemática —AST sobre
`scripts/` para código huérfano, fila por fila sobre las cuarenta filas `HECHO` de la matriz, y
contraste entre persona, contrato, prompt de Creator y plugin— encontró siete afirmaciones más que
eran ciertas del documento y falsas del producto. **E7:** el veredicto derivado se prometía en tres
sitios y `stack.derived_verdicts` no lo llamaba nadie, así que un hallazgo verificado en parte no
tenía veredicto en ninguna parte. **E8:** las métricas se escribían y `metrics.summarize` no las
agregaba nunca. **E9:** al RSI le faltaba la mitad de la reflexión —el gate rechazaba y tiraba la
razón, y el siguiente intento pagaba una corrida de agente para recibir la misma respuesta—. **E10:**
la cobertura de stacks no era falsable; editar el documento para afirmar una campaña que no ocurrió
dejaba las pruebas verdes. **E11 y E12:** once regresiones no corrían sin runtime y la cuenta no lo
decía, y cinco comandos que funcionaban no estaban en `docs/usage.md`. **E13:** el contrato emitido se
medía en bytes pero no se validaba contra su schema. **E14:** siete funciones públicas sin un solo
llamante de producto, siete cableadas y una eliminada por ser un segundo lector del que ya se ocupa
el plugin. Todos con canario: romper cualquiera de ellos hace fallar la suite.

**F5 capa B (índice local del codebase) DECLINADO, no pendiente.** El motivo está medido y escrito
en el borrador: duplica el alcance que `dsh-tool-fs-search` ya da a todo modo generado, sus
dependencias no son distribuibles en este árbol, y su propio invariante lo saca del árbol de lo que
el framework acierta.

**Tercera auditoría: lo que solo se comprobaba contra un fixture.** Las dos rondas anteriores
buscaban afirmaciones de prosa sin contraparte en el código. Esta cambió de dirección: qué reglas
del repositorio se comprueban únicamente contra un fixture, y por tanto nunca tocarían el único
caso real que existe. **E15:** el invariante «plan listo ⇒ comando ejecutable» se probaba para once
productos sintéticos, y el `improvement-verification.json` del propio framework no lo resolvía
ninguna prueba; como `stack.declared()` valida forma y no ejecución, un comando truncado seguiría
resolviéndose `verification_ready: true` y una campaña real habría registrado un fallo del producto
causado por la declaración del framework. **E16:** de los veintidós schemas, tres los aplicaba un
validador escrito a mano al que ningún nombre apuntaba, y dos se direccionaban con un nombre que no
era el de su archivo; ahora la unión está declarada en el producto y la regresión exige que
`schemas/` y ella se nombren exactamente. **E17:** el README publicaba «743» y «755» a dieciséis
líneas sin decir cuál era vigente; la cuenta se descubre ahora, y una cifra que no coincida tiene que
declararse de otro momento. Los tres con canario.

La hipótesis con la que empezó esa ronda era más fuerte que sus hallazgos: un volcado de `cat`
mostraba el comando declarado sin su argumento, y los bytes del archivo y el plan resuelto
demostraron que no era así. **La sospecha era del renderizado, no del framework** — y el fallo que
buscaba sigue siendo alcanzable, que es exactamente lo que la regresión de E15 impide.

**Cuarta auditoría: las dos poblaciones que nadie leía.** **E18:** los golden manifests de
`fixtures/` existen, según su propio README, para validar los generadores y los validadores, y sus
ficheros no llevan rutas ni credenciales — y ninguna prueba, validador ni módulo abría nada bajo
`fixtures/`. Los cuatro manifiestos validan hoy contra sus schemas y se comprueban en cada corrida,
igual que el saneado que el README daba por hecho. **E19:** `prepare_project_skills` copiaba las
skills **sin parsearlas** y seleccionaba directorios por la mera presencia de `SKILL.md`, así que una
skill que ningún cargador leería se instalaba sin decir nada y un directorio con contenido sin
`SKILL.md` se quedaba atrás sin que el resultado lo nombrara. Ahora falla cerrado en los dos casos y
comprueba las cinco skills reales del repositorio. La prueba que cubría ese camino usaba una skill
con saltos de línea literales que solo pasaba porque nadie la leía.

**Sexta ronda: la regla del árbol canónico, sin comprobación (E21).** `AGENTS.md` exige que los
artefactos de ejecución vivan fuera del repositorio y dice expresamente que ignorarlos en Git no
basta, pero solo había `.gitignore`: nada impedía que un `work-items.json` o un `mode-state/` se
quedaran dentro. Ahora la suite falla por nombre ante cualquiera de ellos, con el vocabulario leído de
los literales de `scripts/` y un segundo test que relee esos literales para que la copia no se quede
obsoleta —que es como aparecieron `evidence-ledger.jsonl` y `scenarios.jsonl` en su primera corrida—.
`fixtures/` queda exento por diseño y sujeto a su propia regla de saneado.

**E22 · dos guardarraíles que AGENTS.md pedía y nadie había puesto.** La regla de «sin rutas locales
del mantenedor» sí se comprobaba, pero solo sobre `*.md`, `*.mjs`, `*.py` y `*.sh`: un schema o un
preset se publican igual que un documento, y la búsqueda ahora cubre también `*.json` y `*.yml`.
Y E12 comprobaba que todo subcomando esté documentado pero no que **todo flag documentado exista**,
que es el fallo que se descubre en la terminal del operador en pleno vuelo. Ambos con canario.

**E23 · la promesa de privacidad contra un fichero sin secretos.** El README afirma que el framework
nunca lee ni pide API keys, y el chequeo de proveedor documenta que solo devuelve estructura. El
fixture que usan todos esos casos escribe un `settings.yaml` sin ningún valor de llave: la promesa se
comprobaba contra un fichero que no tenía nada que filtrar, y habría seguido cumpliéndose aunque la
función devolviera el documento entero. Ahora hay secretos en el fixture, bajo varios nombres de
campo, y ninguno puede aparecer en lo devuelto.

Suite de regresión: ver último registro en `CHANGELOG.md`; la suite completa corre en verde antes de cada cierre de unidad.
