# Cambios

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
