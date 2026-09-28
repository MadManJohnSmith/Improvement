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
| Política anti-escalada de sandbox | HECHO | el plugin del framework retira `sandbox_permissions`/`justification` de los schemas de tools y guarda la escalada de bash, corrige el mismo-modo en `workflow_write` (overlay vía `dsh web --patch`), y el prompt prohíbe el canal completo con relevo a cualquier delegado |
| Transacción con veredicto Host | HECHO | `install` exige `host-verdict.json` ACTIVE ligado a la misma generación antes de activar |
| Aceptación Host aislada del Creator | HECHO | harness de aceptación del Host con evaluador y revisor aislados, casos ocultos con predicados privados, cardinalidad completa exigida y actores correlacionados con turnos reales de DSH; aceptación previa determinista (`READY_FOR_INSTALL`), sin afirmación de evaluación dinámica |
| Instalación de modos como presets DSH | HECHO | modos con `mode.json`/`preset.yml`/`agent.cordis.yml`/`SKILL.md`; Creator recibe del run los basenames reales case-sensitive de producto/workspace y la ruta exacta de `mode-state`, y el Host contrasta esa identidad estructurada antes de aceptar/instalar; instala un bundle `@deepseek-ai/dsh-agent-preset`, exige `application=applied`, roster sano y composición/raíz candidatas vía `agentPresets/read`; una actualización `restart-required` queda recuperable hasta relanzar DSH y repetir `bootstrap install` |
| Gate operativo y skills bundle-local | HECHO | composiciones fail-closed con las seis filas operativas, `dsh-tool-fs-search` configurado con `sampleOverCapGlobResults: false` y sin delegación/workflow/web/plugin-manager; frontmatter mínimo de modos/skills; copia completa y segura a `bundle/skills`, `includeDefaultRoots: false`, root absoluto del bundle y ambos IDs en recibo |
| Handoff durable y candidato automático | EN CURSO / IMPLEMENTED_NOT_VERIFIED | contrato/bootstrap/persona, schemas/caps, preflight/migración conservadora, archivo transaccional por digest de evidencia inesperada y originales esperados incompatibles (source path/motivo/digest; 8 MiB/archivo y 32 MiB totales), proyección estricta solo de registros válidos o mapeos inequívocos, candidato digest y límites de commit implementados con regresiones. La reanudación sucia usa `resume_policy: exact-recorded-dirty-only`: antes de provisionar lee el `candidate` estricto de `work-items.json` y solo acepta el target determinista exactamente registrado con estado `DIRTY` o `RETAINED` pendiente de verificación, mismo path/branch/base/digest de hallazgos, identidad worktree y HEAD base, canonical limpio e inalterado, diff candidato no vacío con digest y lista completa de paths coincidentes, confinados a archivos regulares sin symlinks ni submódulos. Un comando central separado valida la reanudación sin exigir candidata limpia ni cambiar bytes; registro ausente o discrepante conserva la colisión `RETAINED` y nunca adopta un worktree sucio arbitrario. Regresiones cubren dos turnos, rechazo de digest/path/base/status o registro ausente, rutas inseguras e invariancia canónica. El startup exige primera bash sin override (workdir omitido o `.`) y un `first_bash_command` exacto centralizado que empieza por `set -eu`, imprime `pwd`, valida basename/producto/workspace en un único `test` y solo entonces emite `__IMPROVEMENT_LAYOUT_OK__`; lifecycle y persona exigen ese `success_sentinel` exacto para continuar y retienen ante su ausencia o resultado no disponible, sin exigir marcador de exit code 0 porque DSH lo omite en éxitos. El cwd esperado es el basename del padre común real de producto/workspace. Auditor conserva candidata previa, incluido `INTEGRATED`, que solo Host/operador puede registrar. Lifecycle/persona lo fijan estructuralmente sin incrustar ruta absoluta del mantenedor. El Auditor declara además `bash_workdir: session-cwd-only-all-calls`: toda bash omite workdir o usa `.`, reescribe antes de invocar comandos para apuntar al producto mediante `git -C`/`npm --prefix`/`cargo --manifest-path` o equivalente, y cualquier override accidental retiene inmediatamente; Repair provisiona desde el cwd de sesión con workdir omitido y comando central exacto: calcula el destino absoluto con `$PWD`, crea el worktree hermano mediante `git -C ./<producto>` y verifica realpath/registro; después usa como workdir exactamente el nombre candidato relativo al cwd de sesión, nunca `.` ni una ruta anidada bajo producto. Schema, validador y persona exigen esos campos y `unrelated_candidates: ignore-preserve`; el preflight central comprueba solo invariantes canónicos y path/branch target, reutiliza únicamente esa identidad exacta y no bloquea ni altera worktrees ajenos clean, dirty o stale. Regresiones ejecutan el comando en repos temporales, prueban sibling/HEAD/rama/registro/limpieza canónica, reutilización exacta, preservación de múltiples candidatas ajenas y rechazo de colisiones del target. Falta repetir la prueba DSH real; bash conserva alcance de escritura del padre y la actualización multiarchivo ordinaria no tiene CAS/lease: no se afirma aislamiento ni atomicidad concurrente |
| Piloto tardis (Syncify) | EN CURSO | cada salida del piloto se convierte en cambio de flujo y regresión; la generación completa con paquete aceptado sigue siendo la salida pendiente |

Suite de regresión: ver último registro en `CHANGELOG.md`; la suite completa corre en verde antes de cada cierre de unidad.
