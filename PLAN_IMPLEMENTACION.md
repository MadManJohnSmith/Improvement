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
| D1 | CAS/lease o escritura atómica multiarchivo de `mode-state` | PARCIAL 2026-09-30 | Lease por fichero con TTL de 30 s: cierra el reemplazo concurrente del mismo fichero. La atomicidad del lote de cinco ficheros **no** se cierra —el backend no ofrece transacción— y sigue declarada en `write_method` |
| D2 | Confinamiento mecánico de bash del auditor | PENDIENTE · premisa corregida 2026-09-30 | **La razón registrada antes era falsa y queda corregida.** El runtime DSH instalado (`0.1.5-alpha.1`) **sí** ofrece confinamiento mecánico: `dsh-sandbox-policy` con `read-only`/`workspace-write`/`danger-full-access` y `read-only` como default fail-safe, más `dsh-bash-sandbox`/`dsh-fs-sandbox` sobre bwrap (Linux, verificado en esta máquina: `EROFS` real, "Read-only file system", producto intacto) con Landlock y Seatbelt como alternativas. No hace falta "ver qué modos ofrece": ya se leyeron en el código y se probaron. El bloqueo real es otro y es de diseño, no de capacidad: (a) `dsh-agent-presets` **rechaza** que una fila de preset publique un servicio global, así que un modo **no puede montar su propia `sandboxPolicy`** — la política es de la composición anfitriona, luego el modo no declara su modo y solo lo hereda; (b) `read-only` no sirve para el auditor porque `checkedTarget` deniega **toda** mutación de `ctx.fs`, y sus propias escrituras de estado pasan por `workflow_write` → `ctx.fs.writeText` con la política resuelta, así que el modo auditaría y no podría persistir nada; (c) `workspace-write` deja escribir el producto, porque la raíz escribible es el **cwd de sesión** y el producto es hermano del workspace *dentro* de ese cwd. Cerrarlo exige mover el producto fuera de la raíz escribible (cambiar el layout, no la política) o un canal de escritura que no pase por `ctx.fs`. Ninguna de las dos es un parche de composición, y por eso sigue abierta |
| D3 | Gate de reconteo `persisted_count` contra el fichero | HECHO 2026-09-30 | `count_command` central que recalcula el conjunto abierto desde el fichero e imprime el número; el handoff debe cubrir exactamente ese conjunto y `workflow_write` lo rechaza si no |
| D4 | Aviso y re-apuntado asistidos ante reescritura de commits tras integrar | HECHO 2026-09-30 | `bootstrap.py state` lo detecta (`integrated_head_rewritten`) y `--repoint` solo acepta revisión ancestro del HEAD canónico con producto limpio, con recibo en `overflows.jsonl` |
| D5 | Retirada de candidata como mecanismo verificado, no procedimiento | HECHO 2026-09-30 | `bootstrap.py state --retire` verifica condición por condición y es idempotente; el procedimiento manual de `docs/usage.md` queda como explicación, no como paso |
| D6 | Enum de `verification-results`: `PARTIAL` entra o se exige enum cerrado con N/A justificado | DECIDIDO 2026-09-30 | El enum sigue cerrado y `PARTIAL` pasa a ser veredicto **derivado** por hallazgo (peor resultado gana: FAIL > BLOCKED > PASS), con un registro por entrypoint; `REPAIRED` no entra |
| D7 | Hallazgo rico (fingerprint, causa, prevención de recurrencia) en `mode-state` | HECHO 2026-09-30 | `evidence.path`+`excerpt` con `line`, `located` y `fingerprint` calculados por la herramienta; `cause` y `prevention` acotadas a 256 B y el cap de 4.096 B del registro comprobado en el límite de escritura; reparto `anchors` en `bootstrap.py state`. Los tres campos nuevos son opcionales, así que la evidencia histórica no se archiva |
| D8 | Vista derivada de hallazgos cerrados por work item VERIFIED | HECHO 2026-09-30 | `bootstrap.py state` nombra `closed_findings` y `uncovered_findings` sin reescribir el ledger |
| D9 | Directorio de evidencia fuera de `mode-state` para parches y logs grandes | HECHO 2026-09-30 | Raíz gestionada `<workspace>/evidence` con topes propios (8 MiB/fichero, 256 MiB, 200 ficheros, nombre seguro) y recibo en `overflows.jsonl` al descarter; `workflow_write` la acepta y sigue negando todo lo demás |
| D10 | Plantilla que distinga auditoría completa de incremental (anti-anclaje) | HECHO 2026-09-30 | `audit_scope` en el contrato y la persona: en completa se observa antes de leer la cola, en incremental se parte del diagnóstico; el alcance viaja en el `handoff_id` y `bootstrap.py state` cuenta ambos |
| D11 | Paquete de memoria F5, RSI y disparador por commit | PARCIAL 2026-09-30 · obstáculo corregido 2026-09-30 | El gate de RSI está implementado y probado (`scripts/skill_gate.py`, `bootstrap.py skill-gate`): holdout disjunto, aceptación solo por mejora estricta, rechazo por regresión en entrenamiento y abstención sin evidencia. **La razón registrada antes —"falta correr los escenarios contra un modo DSH real"— era incompleta:** comprobarlo muestra que los 55 escenarios de `library/` **no son ejecutables tal cual**. Su `input` es una tabla de aserciones declarativas sobre una situación (`contract_declared: true`, `attempted_write: true`), no una tarea que un agente pueda recibir; los ficheros no llevan `target_mode` ni prompt, y solo uno de 55 tiene un campo `task`. Instalar un runtime no bastaría: hay que darles forma ejecutable primero. **La forma a copiar ya existe y es barata**: `acceptance_harness._public_input` materializa la misma idea con `task`, fixture acotada y `evaluated_claim`, y su vocabulario de tipos (14) cubre **los 8** que usa este corpus. Los dos corpus están desconectados —fuera de `skill_gate` nada lee `library/` y el harness genera sus propios casos Host—, así que conectarlos es trabajo de autoría sobre una plantilla probada, no maquinaria nueva. Siguen sin decidir F5 (memoria episódica e índice) y el disparador por commit |
| D12 | Publicación de la beta (tag y push) | BLOQUEADO | G6 requiere autorización de destino |

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
