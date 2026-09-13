# Plan de pendientes para el cierre del núcleo

**Estado:** planificación descriptiva; no implementación ni acreditación de resultados. Ningún hito de este documento está ejecutado ni aceptado hasta que el estado comprobado lo registre.
**Fecha de referencia:** 2026-09-13.
**Destinatario:** agente de mantenimiento autorizado para ejecutar misiones de cierre.
**Jerarquía:** subordinado a [ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) (diseño vigente), [PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md) (único índice de progreso), [docs/status.md](status.md) (estado comprobado) y [AGENTS.md](../AGENTS.md) (reglas del repositorio).
**Antecedente directo:** [PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md](PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md), ejecutado en P0–P9 el 2026-09-13 (ver hito «Misión de cierre integral en copias aisladas» en status.md). Este documento organiza **solo lo que queda**; no abre otro backlog: las filas de PLAN_IMPLEMENTACION.md siguen siendo la única fuente de estado.
**Nota:** escribir este plan no ejecuta nada. Cada hito conserva `PARCIAL`/`PENDIENTE` hasta que su gate quede acreditado con evidencia externa y el índice se actualice.

## 0. Base operativa heredada de la misión del 2026-09-13

Estos hechos comprobados condicionan cómo ejecutar los hitos siguientes; re-verificar al retomar (versiones de runtime, rutas y servicios pueden cambiar):

1. **Rig reutilizable.** El directorio externo `Improvement-ensayos/mision-arq-20260913/rig/` contiene el rig completo probado: `rig_launch.py` (orquestador host-side: bwrap fail-closed + canal de inferencia + presets + credencial nrouter leída en memoria, nunca impresa), `rig_check.mjs` (Host web aislado, sesión por preset con 8 skills, workspace escribible en `/state/ws` con copia del producto, modo de sesión `read-only` + hook de aprobación auditado), `consolidate_unit.py` (recibos crudos → contrato v1 → `run_check`/`verify`/`reaudit` → lote del publicador). Reutilizarlo tal cual; cualquier cambio al rig es cambio de ensayo, no del framework, y se registra.
2. **Coste medido por turno real** (fuente: logs de sesión DSH, `state/metricas.json`): 13–61 requests y 0,1–3,0 M tokens de entrada por turno; 28–85 tool calls; duración 10–45 min por turno. Presupuestos de referencia para no agotar el canal: auditoría unitaria acotada ≤ 120–150 requests; reparación ≤ 200–220; `deadline=280`, `messages=256`, `payload_limit=2 MiB`.
3. **Trampas de runtime conocidas (no re-descubrirlas):** (a) el esquema de `bash` induce al modelo a enviar `sandbox_permissions` y el validador rechaza el modo ya vigente («not strictly wider») — el rig lo resuelve con modo de sesión `read-only` + aprobación del titular (auditada en `approval/decided`); la herramienta `write` del runtime sigue fallando en ese caso (ver M7); (b) escritura de evidencia por `bash` con redirección, no por `write`; (c) el entorno del agente ZCode resuelve `sys.executable` al AppImage y contamina subprocesos: ejecutar suites vía `zsh -c` anidado; (d) el publicador agota su almacén a 16 registros: un lote por almacén y almacén nuevo por ciclo (`publisher-store-N`); (e) cada lanzamiento del rig arranca con `/state` nueva: la evidencia entre turnos se traslada con el input `evidence-carry`.
4. **Productos y padres limpios ya incorporados** (idempotentes): `Improvement-ensayos/mision-arq-20260913/copies/padre-{syncify,rehabweb}/` con clon del framework, copia de producto, workspace y enlaces gestionados. RehabWeb requiere `PYTHONPATH=/inputs/deps` (site-packages del venv montado) para sus tests Django.
5. **Límites que no se reabren sin gate propio:** distribución y publicación remotas sin autorización (M8); durabilidad ante pérdida de energía y descendientes remotos (M6); controlador Host real (M3).

## M1 — Consumo de cola completa por proyecto

**Objetivo:** pasar de «unidades seleccionadas por vuelta» a procesar la cola autorizada completa de Syncify y RehabWeb, con la misma cadena por unidad (auditoría → hallazgo → reparación rojo/verde → QA subagente → verify → reaudit → lote COMPLETE).
**Responsables/controles:** coordinador (orden de la cola, deduplicación, presupuesto); Ejecutor y QA como funciones internas del rig; Host del rig para transiciones; mantenedor para commits del flujo si hay defectos.
**Precondiciones:** rig operativo y verificado con humo corto; copias de producto limpias (re-crearlas desde los padres si el ciclo anterior las integró); inventario determinista vigente por producto (`audit.py inventory`); presupuesto de misión fijado en el ledger (`scripts/budget.py`) antes del primer turno.

**Pasos:**
1. Fijar en el ledger los límites de la misión: intentos=2 por unidad (límite vigente, no ampliable sin decisión), tope de requests por turno según §0.2, tope de turnos por sesión. Registrarlo en `started.json` del estado externo.
2. Generar la cola: por cada proyecto, una o varias auditorías completas con `workflow-complete-auditor` que partitionen el inventario (unidad = contrato funcional; `audit.py consolidate` valida la partición `PARTITION_VERIFIED`) y produzcan hallazgos con `change_scope` acotado a archivos Python reproducibles cuando exista productor ejecutable; los hallazgos Rust/TS sin test ejecutable declaran evidencia alternativa necesaria (estática) y quedan rotulados.
3. Deduplicar la cola por fingerprint/causa; reconciliar con las colas históricas ya registradas en status.md (no re-reparar lo ya cerrado: verificar vigencia del hallazgo contra la base actual antes de encolar).
4. Ejecutar la cola en orden de prioridad (seguridad > contrato > calidad) con el patrón probado: turno de reparación → consolidación de recibos → `run_check`/`verify`/`reaudit` → lote del publicador. Un almacén del publicador por ciclo.
5. Unidades sin reparación viable: retener con `RETAINED` + causa + candidato preservado; una unidad retenida no bloquea la cola pero sí el cierre del proyecto (queda en la excepción del informe).
6. Cierre del proyecto: consolidar la matriz hallazgo→evidencia, reauditoría incremental final y lote de cierre con gaps explícitos si los hay.

**Criterios de aceptación:** positivos — cada hallazgo de la cola finaliza en `ACCEPTED` con cadena completa o en `RETAINED` con causa y candidato; cero hallazgos sin estado; las suites del proyecto pasan sobre el conjunto integrado. Negativos que invalidan — consumir el lote sin resolver criterios; reusar aceptaciones de bases distintas; suplantar retención por éxito.
**Evidencia:** recibos v1 + lotes del publicador por unidad; matriz requisito→evidencia por proyecto; métricas acumuladas en `metricas.json`.
**Estimación:** Syncify cola estimada 10–20 unidades, RehabWeb 20–40 (a confirmar con la partición); 2 turnos por unidad ≈ 40–120 turnos totales. Fraccionar en misiones de 5–8 unidades para respetar duración de sesión; el estado externo permite retomar sin reejecutar.
**Riesgos:** presupuesto (mitigado por fraccionamiento y ledger); conflictos entre unidades que tocan el mismo archivo (mitigar ordenando por `change_scope` y reauditando tras cada integración).

## M2 — Reauditoría semántica como turno propio de Auditor

**Objetivo:** que cada reparación aceptada reciba, después de QA, una reauditoría incremental real de Auditor (no solo la mecánica `reaudit` con `PENDING_SEMANTIC_REVIEW`).
**Responsables/controles:** Auditor (sesión/preset de auditoría, modelo distinto del ejecutor); Host del rig para enlazar sesión→candidato.
**Precondiciones:** M1 en marcha (se aplica por unidad, no al final); sesiones observadas distintas por rol (ya comprobado en el rig).

**Pasos:**
1. Tras `verify` ACCEPTED de una unidad, lanzar turno de auditor con encargo acotado: «reaudita la unidad X tras el candidato Y (hashes en recibos); verifica prevención, efectos relacionados y que la cola quedó coherente; no modifiques producto».
2. Exigir del turno un veredicto explícito (`CONFIRMED`/`REOPENED` con causa deduplicada) sobre el informe de la unidad y los hashes del candidato vigente.
3. `REOPENED` re-encola la unidad como nueva causa si es material nueva, o como reintento (cuenta contra los 2 intentos) si es el mismo defecto persistente; sin progreso → retener (§9 arquitectura).
4. Registrar el veredicto como registro `auditor` del lote (etapa ya existe) con `session_ref` real del turno.
5. Solo entonces el cierre del ciclo declara la unidad sin pendientes semánticos.

**Criterios:** positivos — cada `ACCEPTED` del proyecto tiene un veredicto de reauditoría semántica enlazado al hash del candidato aceptado, emitido por sesión distinta del ejecutor y del QA. Negativos — reutilizar la QA como reauditoría; aceptar veredicto sobre candidato de otro hash.
**Evidencia:** recibos `reaudit-semantica.json` por unidad + evento de etapa `auditor` del lote.
**Estimación:** +1 turno corto por unidad (30–60 requests). Puede combinarse con M1 (mismo ciclo de misión).
**Nota:** la independencia estadística entre sesiones del mismo modelo no se garantiza (§3 arquitectura): se declara como separación de roles observada, no como independencia estadística.

## M3 — Controlador Host real

**Objetivo:** sustituir el orquestador manual (los scripts del rig ejecutados por el mantenedor) por un controlador Host que gestione el ciclo de la misión desde estado persistente: cola, presupuesto, locks de escritor, transiciones y reconciliación.
**Responsables/controles:** Host (persistencia, autorización efectiva, exclusión de escritores, cancelación); mantenedor (diseño y aceptación); usuario (recursos y límites).
**Precondiciones:** servicios ya probados (`missions.py`, `publisher.py`, `budget.py`, launcher, canal); contrato de reconciliación de `tests/test_recovery_durable.py` es la especificación que debe satisfacer.

**Pasos:**
1. Diseño mínimo (documento corto + decisión registrada en CHANGELOG): el controlador es un proceso Python stdlib sin LLM propio; cada transición llama a los servicios existentes; nada de parches ocultos al runtime. Estado en directorio externo por misión (`state/host/`): `mission.json` (mandato+base), `queue.json` (cola canónica), `ledger/` (budget.py), `locks/` (flock por unidad), `events.jsonl` (append-only).
2. Implementar el bucle: tomar siguiente unidad lista → reservar presupuesto → lanzar el turno del rig (subproceso con `rig_launch.py` adaptado o API equivalente) → consolidar recibos → verify → reaudit → publicar lote → marcar unidad. Todo con checkpoint en cada transición (`checkpoint.json`, `report.md`, `finish.json` según §7 arquitectura).
3. Reconciliación al arrancar: unidades en vuelo sin cierre → reconciliar antes de relanzar (idempotencia ya probada en fixtures; aquí contra el rig real).
4. Cancelación y timeout del controlador: señal → matar descendientes locales (flock ya probado), preservar presupuesto y candidato, dejar `RETAINED` con siguiente acción.
5. Regresiones nuevas del framework: `tests/test_host_controller.py` con el rig en modo determinista (fixture de turno que responde con recibos pregrabados) cubriendo: consumir 3 unidades, agotamiento, caída del controlador en cada transición, doble arranque (lock), cancelación.
6. Ensayo real: una misión de 3–5 unidades (M1) ejecutada íntegramente por el controlador sin intervención por unidad; el mantenedor solo inicia y recoge el cierre.

**Criterios:** positivos — ciclo completo sin transporte humano de recibos ni prompts por unidad; reinicio del controlador en cualquier punto reanuda sin duplicar escritor ni consumo; el ledger no reinicia gasto. Negativos — el controlador edita el framework para lograr verde; concede autoridad por sí mismo; salta QA.
**Evidencia:** ejecución real del controlador (logs de eventos), suite nueva en verde, comparativa de coste con la ejecución manual de M1.
**Estimación:** implementación 1–2 sesiones de mantenimiento + 1 misión de ensayo real.

## M4 — Aceptación integral por proyecto

**Objetivo:** retirar el `PARCIAL` de las etapas 5 y 8 con la aceptación integral de Syncify y RehabWeb.
**Precondiciones:** M1 (cola completa), M2 (semántica), M3 (controlador, recomendado pero no bloqueante si M1 se ejecuta con el rig manual).
**Pasos:** 1) reconciliar todas las colas/lotes de ambos proyectos en una matriz requisito→evidencia; 2) reauditoría final por proyecto sobre la copia integrada; 3) suite completa de cada proyecto en verde sobre el conjunto; 4) archivo restaurable por proyecto con manifiesto; 5) actualizar filas del índice (etapas 5 y 8) y status.md; 6) informe de cierre con excepciones explícitas si quedan unidades `RETAINED`.
**Criterios:** cero unidades sin evidencia al declarar aceptación; una excepción declarada no rebaja gates del núcleo (queda como límite, no como silencio).

## M5 — Memoria de decisiones y métricas finas instrumentadas

**Objetivo:** implementar el contrato de §7 (decisiones con identidad estable) y §15 (métricas por rol) como servicios locales reales, no solo instrucciones.
**Pasos:**
1. `scripts/decisions.py`: almacén externo append-only por misión con `decision_id`, versión, motivo, alternativas descartadas, unidades afectadas, estado vigente/sustituido (referencia al reemplazo); el encargo recupera solo las pertinentes; el ejecutor declara preserva/sustituye; QA evalúa la declaración; el cierre actualiza referencias. Regresiones: creación exclusiva, sustitución material exige autorización, lectura por unidad.
2. `scripts/metrics.py` (o extensión de `budget.py`): eventos por turno desde los logs de sesión DSH (requests, tokens in/cache/out por rol, denegaciones, reintentos, rondas) con fuente y unidad; nada se reconstruye de memoria; lo no observable queda «no disponible», nunca 0.
3. Integración en el ciclo: el controlador (M3) o el consolidador del rig escribe eventos al cerrar cada turno; comparación baseline vs delegación solo entre misiones de igual alcance/aceptación (usar los datos del 2026-09-13 como primera línea base).
4. Memoria episódica privada con TTL y cuotas: opcional y separada; solo si M5.1–3 están en verde.
**Criterios:** decisiones recuperables por unidad tras reinicio; sustitución material sin autorización falla cerrada; métricas de una misión reproducibles desde eventos persistidos. **Estimación:** 1–2 sesiones.

## M6 — Durabilidad y descendientes remotos

**Objetivo:** mover de «límite documentado» a «probado» lo ensayable localmente, y dejar explícito lo que exige hardware/decisión.
**Pasos:**
1. Pérdida de energía simulada: ejecutar el controlador (M3) en una VM contenedor con pausa/crash del hipervisor (o `SIGKILL` al árbol completo incluyendo bwrap) en los tres puntos de transición; comparar con la atomicidad ya probada (rename/OS sync). Si el entorno no permite crash real, el gate queda abierto y se documenta.
2. Descendientes remotos: definir protocolo mínimo de ejecución incierta (identificador de ejecución remota + consulta de estado + cancelación si el servicio lo ofrece); con nrouter no aplica (broker sin procesos remotos), con cualquier runner futuro sí. Sin protocolo real, mantener el límite y no declarar control.
3. Registrar resultados en status.md como capacidad o como límite, con la prueba exacta.
**Criterios:** tras crash completo, el estado externo reconstruye la misión sin subcontar presupuesto ni duplicar escrituras; o el gate queda abierto con causa de entorno. **Estimación:** 1 sesión + entorno de VM.

## M7 — Defecto runtime: `write` rechaza el modo vigente (RESUELTO como plugin, 2026-09-13)

**Situación:** el runtime DSH instalado (0.1.5-alpha.1) rechaza con «not strictly wider» las escrituras que solicitan el mismo modo ya vigente, bloqueando la herramienta `write` del agente con enforcement completo; el workaround actual (bash + modo `read-only` de sesión + aprobación) está probado pero es un rodeo.
**Resolución adoptada (decisión del titular):** `scripts/dsh-plugins/workflow-write.mjs` montado en los presets del flujo con regresión `tests/test_workflow_write_plugin.py`; el runtime instalado no se parchea. **Pasos restantes:** 1) consolidar el informe del defecto con las tres sesiones de evidencia y el transcript de producción ya registrado; 2) reportarlo al mantenimiento del runtime (el titular decide canal: upstream, parche local versionado del paquete instalado, o convivencia con el workaround); 3) si hay corrección upstream, repetir la sonda de escritura y retirar el rodeo del rig con regresión; 4) actualizar setup-dsh.md (escenarios conductuales (1) y (3) siguen pendientes de ejecución: incorporarlos a la misma sonda).
**Criterios:** sonda de escritura ordinaria del agente pasa sin escalada en modo vigente; escenario (2) de setup-dsh.md deja de reproducirse. **Bloqueo real:** decisión del titular sobre cómo tratar el paquete instalado.

## M8 — Distribución y publicación remotas (decisión titular)

**Situación:** probado solo bundle local (clon/directorio); sin autorización de red para origen/destino no se puede acreditar la distribución remota (§14, §17) ni publicar.
**Pasos cuando haya autorización:** 1) definir origen autorizado (repo remoto del titular) y destino; 2) bootstrap clean-room desde descarga con versiones fijadas y manifiesto de procedencia/hash; 3) repetir P1+P7 de la misión anterior desde esa descarga; 4) publicación solo tras revisión de diff, licencia decidida por el titular y push explícito.
**Criterios:** incorporación desde cero en máquina limpia vía red; repetición idempotente; sin credenciales ni datos privados en la distribución. Sin autorización, este hito permanece `BLOQUEADO` y no bloquea el núcleo local.

## Orden de ejecución y dependencias

```text
M7 (decisión titular, paralelizable)   M8 (bloqueado hasta autorización)
        │
M1 ──► M2 (por unidad, dentro del ciclo de M1) ──► M4 (cierre por proyecto)
        │
        └──► M3 (controlador; puede empezar en paralelo y ensayarse con un tramo de M1)
M5 (instrumentación; conviene antes de agotar M1 para no perder métricas de las colas)
M6 (requiere M3 para crash real; si no, queda abierto)
```

Recomendación de secuencia en misiones: (1) M5.1–2 + arranque de M1 (primeras 5 unidades Syncify); (2) M3 + M1 continúa bajo controlador; (3) M2 por unidad desde el inicio de M1; (4) M4 por proyecto al consumir su cola; (5) M6 con el controlador estable; (6) M7/M8 según decisión del titular.

## Trazabilidad

| Hito | Etapas del índice | Secciones de arquitectura |
|---|---|---|
| M1 | 5, 8 | §7 ciclo, §13 cobertura, §16 |
| M2 | 5, 8 | §9 aceptación, §13 profundidad |
| M3 | 7 | §7 persistencia, §12 intervención, §15 adaptador |
| M4 | 5, 8 | §2 objetivo, §16, §17 |
| M5 | 6 | §7 memoria de decisiones, §15 métricas |
| M6 | 7 | §8 durabilidad, §12 |
| M7 | 0 | §11 seguridad, §15 límites del adaptador |
| M8 | 0, 8 | §14 distribución, §17 aceptación |

## Formato de entrega por hito

Cada misión que ejecute uno de estos hitos entrega: resumen corto con estado del hito; gates aprobados/faltantes con evidencia externa por referencia; comandos e intervenciones reales (preparación separada de uso normal); coste observable con fuente; retenciones y pruebas omitidas; y, si hay bloqueo real de autoridad/recursos, excepción breve con decisión mínima necesaria — sin declarar completitud por actividad ni usar un cierre parcial como salida rutinaria.
