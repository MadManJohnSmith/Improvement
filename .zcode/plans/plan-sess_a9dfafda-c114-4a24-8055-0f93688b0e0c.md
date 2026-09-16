# Plan de cierre de versión con configuración de modelos aprobada

## Decisión registrada

El usuario autorizó (enmienda al plan aprobado) configurar **presets propios persistentes** con este mapping de modelos del proveedor nrouter (9router):

- **Auditoría / orquestación (modo Auditor):** `nrouter/Orquestrador` (RAW), en sesión de orquestador.
- **Subagentes de QA/auditoría:** `nrouter/subagents-audit`.
- **Subagentes de ejecución/reparación:** `nrouter/subagents-coding`.

Reglas que se mantienen: no tocar presets distribuidos ni routing global del Host activo; las credenciales y secretos no se leen, copian ni publican; todo ensayo en instancia/estado aislados y artefactos externos; sin push. `nrouter/Orquestrador` devolvió `EMPTY_RESPONSE` en la prueba anterior; si vuelve a fallar con esta composición se retiene y se informa, sin cambiar el mapping sin autorización.

## Fase A — Configuración de modelos en presets propios (hito previo exigido por el usuario)

1. **Catálogo y contrato primero (verificación, no suposición):** comprobar mediante una llamada mínima en instancia aislada que `nrouter/subagents-audit` y `nrouter/subagents-coding` existen y responden; si el catálogo los rechaza, retener con el error exacto del proveedor (sin fallback silencioso) y notificarlo como bloqueo.
2. **Composición externa de presets propios** (destino autorizado: workspace externo, p. ej. `/home/alan/DSH-workspace/` en directorio nuevo dedicado, nunca dentro del canónico ni `~/.dsh`): dos presets con `preset.yml` + `agent.cordis.yml` según el esquema de `docs/creator-preset-spec.md`, extendido a Reparación:
   - `auditor-preset`: fila de orquestador fijada a `provider/model = nrouter/Orquestrador`; monta skills `workflow-auditor`/`workflow-complete-auditor` por origen explícito (copias vigentes del workspace, sin enlaces inventados); filesystem lectura producto/framework; escritura solo evidencia/cola; subagentes habilitados SOLO con `subagent-model-selection.allowedModels = [nrouter/subagents-audit]`.
   - `repair-preset`: misma estructura para `workflow-continuous-repair`; `allowedModels = [nrouter/subagents-coding]` para ejecución y `[nrouter/subagents-audit]` para su QA de solo lectura si el runtime lo permite por rol; escritura solo workspace/ciclo externo.
3. **Carga y prueba de aceptación (sin auditoría real en este paso):** arrancar Host aislado con `host_launcher.py`, crear sesión con cada preset, verificar: modelo efectivo por sesión (orquestador) y por spawn de subagente (audit/coding), carga nativa de skills con origen/cuerpo, routing global sin cambios, y una llamada de humo mínima por modelo (sin datos de producto).
4. **Regresión permanente:** test que fixture el preset y afirme mapping efectivo y rechazo de modelos no listados en `allowedModels` (fail-closed), sumándose a la suite Python/Node existente.

## Fase B — RehabWeb: segundo ciclo real (cierre del Hito 6 del plan)

1. **Mandato de escritura:** el usuario ya aprobó terminar el plan; el checkpoint exige "candidato escribible + mandato de escritura". Se usa el workspace de RehabWeb existente (`session-rehabweb-2`), sin read-only: la misión declara alcance por unidad (`change_scope` de la cola vigente).
2. **Ejecución de la cola:** consumir `repair-queue.json` (52 listos, 4 retenidos previos, 53 propuestas) con el preset de reparación: por unidad → candidato externo → prueba verde → QA subagente independiente (`subagents-audit` para QA, `subagents-coding` para ejecución) → reauditoría → solo integración en copia de ensayo de RehabWeb. Las propuestas históricas sin candidato/prueba/QA no se marcan reparadas; se re-trabajan o se retienen con evidencia.
3. **Criterios de parada:** presupuesto de intentos (máx. 2 correcciones por unidad), coste/tiempo; lo no verificable queda `RETAINED` con excepción concreta; nunca `ACCEPTED` nominal.
4. **Evidencia externa:** recibos, lotes y archivo bajo `session-rehabweb-2/cycles/...` siguiendo el formato Syncify ya probado.

## Fase C — Recuperación durable y operación continua (Hito 5)

1. Sobre la misión RehabWeb (o re-simulación determinista si la cola termina antes), inyectar: timeout de turno, cancelación, caída de worker y reinicio del Host aislado en tres puntos: antes de publicar, después de publicar/antes de ack, durante QA.
2. Afirmaciones a comprobar con evidencia: cero escritores duplicados, cero integración repetida, candidato/estado conservados, presupuesto no reiniciado, QA invalidada si cambia el candidato.
3. Continuidad: consumir unidades siguientes de la cola en una sola sesión con límites persistentes (estado en workspace externo), demostrando operación normal antes que recuperación.

## Fase D — Cierre de versión

1. Suite completa con `DSH_MODULE_ROOT` configurado (elimina el skip de `test_host_launcher.py`), incluida la nueva regresión de presets y los 3 escenarios conductuales pendientes de `docs/setup-dsh.md` si el routing lo permite.
2. Actualizar `docs/status.md`, `ARQUITECTURA_FLUJO_AGENTES.md`, `PLAN_IMPLEMENTACION.md` (filas 5–8) y `CHANGELOG.md` solo con evidencia real; revisión completa del diff.
3. Commit local final del flujo (sin push). Informe final: qué quedó acreditado, qué quedó retenido y los comandos exactos para reproducir.

## Ejecución

Autónoma por fases, subagentes especializados por fase (A config/presets, B ciclo RehabWeb, C recuperación, D cierre), sin interrupciones salvo bloqueo material (catálogo que rechace los modelos, o proveedor caído). Artefactos y evidencia fuera del canónico; productos originales intactos salvo copia de ensayo.