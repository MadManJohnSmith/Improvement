# Progreso agéntico de Improvement — vista de una página

**Actualización:** 2026-10-11 (estado derivado de ensayos externos, sin afirmar que las modificaciones locales estén integradas).

**Qué es este documento:** una sola lectura del estado de **todos** los hitos
C/D/E/F/G/M/P/U y B0–B4, con el estado derivado de la evidencia citada y no de la
intención. `PLAN_IMPLEMENTACION.md` sigue siendo el índice de progreso; este archivo
es su vista conjunta, para que ningún identificador quede sin buscar.

**Vocabulario (tomado, no inventado):**

- `HECHO` — `PLAN_IMPLEMENTACION.md:17`: salida y gate comprobados con evidencia recuperable.
- `PARCIAL` / `DECIDIDO` / `DECLINADO` / `RETENIDO` / `PENDIENTE` / `BLOQUEADO` — vocabulario de `PLAN_IMPLEMENTACION.md:18-21`. `RETENIDO` es candidato preservado, no aceptado, y no es `DECLINADO`.
- `IMPLEMENTED_NOT_VERIFIED` / `EN CURSO` — vocabulario de `docs/status.md:4`.
- `RETIRADO` — lo que `docs/status.md:28-34` llama «Eliminaciones de vigencia».

**Cómo leer las columnas.** *Estado derivado* es lo que la evidencia citada sostiene
hoy. *HUS* distingue los hitos cuyo pasado se reutiliza por Git (`git show`) de los que
siguen vivos en el árbol.

---

## B0–B4 · Base MVP comprobada (nomenclatura previa a C0–C7)

| ID | Qué fue | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| B0 | Onboarding, skills, Host aislado y canal DSH | HECHO | vivo | `PLAN_IMPLEMENTACION.md:27`; `scripts/onboard.py`, `scripts/host_launcher.py`, `scripts/inference_channel.py` |
| B1 | Auditoría, reparación, QA y reauditoría reales | HECHO | vivo | `PLAN_IMPLEMENTACION.md:28`; `scripts/missions.py`, `scripts/publisher.py` |
| B2 | Controlador, presupuesto, memoria y métricas | HECHO | vivo | `PLAN_IMPLEMENTACION.md:29`; `scripts/host_controller.py`, `scripts/budget.py`, `scripts/decisions.py`, `scripts/metrics.py` |
| B3 | Plugin de escritura y distribución privada | HECHO | vivo | `PLAN_IMPLEMENTACION.md:30`; `tests/test_workflow_write_plugin.py` |
| B4 | Núcleo fail-closed en dos proyectos | HECHO | vivo | `PLAN_IMPLEMENTACION.md:31` |

Límite conservado de la familia (fila B0): **no equivale al flujo de incorporación 3.0**.

## C0–C7 · Etapas del flujo final (vigentes en el índice)

| ID | Etapa | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| C0 | Contratos generacionales, biblioteca y catálogo | HECHO | vivo | `PLAN_IMPLEMENTACION.md:37` |
| C1 | `bootstrap install` determinista | HECHO | vivo | `PLAN_IMPLEMENTACION.md:38` |
| C2 | Automatización DSH Creator | HECHO | vivo | `PLAN_IMPLEMENTACION.md:39` |
| C3 | Validador Host de generación | HECHO | vivo | `PLAN_IMPLEMENTACION.md:40` |
| C4 | Backups, instalación transaccional y desinstalación | HECHO | vivo | `PLAN_IMPLEMENTACION.md:41` |
| C5 | Aceptación automática DSH | HECHO | vivo | `PLAN_IMPLEMENTACION.md:42` |
| C6 | Piloto clean-room en proyectos nuevos | HECHO | vivo | `PLAN_IMPLEMENTACION.md:43` |
| C7 | Promoción y distribución de piloto | HECHO | vivo | `PLAN_IMPLEMENTACION.md:44` |

**C2 necesita una nota que su fila no lleva.** El 2026-10-10 un turno headless real
con el `creator-prompt.md` del run íntegro **no** persistió `generated/generation-manifest.json`
y el run quedó `RETAINED`. La fila C2 sigue `HECHO` porque su gate propio se cumplió
en su momento; aquel pase **no revalidó C2**. La causa medida fue la falta del overlay
en headless: sin él `write` caía en la fila de upstream rechazada por el sandbox.
Después, el ensayo X3 sí probó `creator_client.dsh_headless_command` con overlay y
una generación real ACTIVE. Esa prueba fue **anterior** al ajuste del presupuesto
Creator por run; no valida una generación post-presupuesto. Ver X2 y X3.

**Aviso de puntero:** `creator-prompt.md` no vive en el árbol canónico; lo
escribe `scripts/creator_client.py:1062` dentro del run dir del workspace
externo, así que solo es citable por run, no por ruta del repo. La nota mantiene
la referencia como nombre de fichero precisamente para no apuntar a un camino
que aquí no existe.

## D1–D9 · Deuda declarada (vigente en el índice)

| ID | Unidad | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| D1 | CAS/lease o escritura atómica multiarchivo de `mode-state` | HECHO 2026-10-01 (con residuo declarado) | vivo | `PLAN_IMPLEMENTACION.md:73`; `tests/test_state_commit.py` |
| D2 | Confinamiento mecánico de bash del auditor | HECHO 2026-10-01 (auditor); E4 cierra el reparador | vivo | `PLAN_IMPLEMENTACION.md:74`; `tests/test_auditor_confinement.py` |
| D3 | Gate de reconteo `persisted_count` | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:75` |
| D4 | Aviso y re-apuntado ante reescritura de commits | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:76` |
| D5 | Retirada de candidata como mecanismo verificado | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:77`; `bootstrap.py state --retire` |
| D6 | Enum de `verification-results` | DECIDIDO 2026-09-30 (aterriza en E7) | vivo | `PLAN_IMPLEMENTACION.md:78` |
| D7 | Hallazgo rico (fingerprint, causa, prevención) | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:79` |
| D8 | Vista derivada de hallazgos cerrados por work item | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:80` |
| D9 | Directorio de evidencia fuera de `mode-state` | HECHO 2026-09-30 | vivo | `PLAN_IMPLEMENTACION.md:81` |

## E1–E9 · Endurecimiento post-C7 (vigente en el índice)

| ID | Unidad | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| E1 | Commit transaccional de `mode-state` | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:85` |
| E2 | Memoria episódica e índice | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:86` |
| E3 | Ejecutor del gate de biblioteca | MECANISMO HECHO; EJECUCIÓN NO | vivo | `PLAN_IMPLEMENTACION.md:87` |
| E4 | Confinamiento del reparador | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:88` |
| E5 | Honestidad de la cobertura de stacks | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:89` |
| E6 | Cerrar el bucle de lectura de la memoria episódica | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:90` |
| E7 | Veredicto derivado calculado de verdad | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:91` |
| E8 | El ledger de métricas se lee | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:92` |
| E9 | La mitad de reflexión del RSI | HECHO 2026-10-01 | vivo | `PLAN_IMPLEMENTACION.md:93` |

El índice canónico sigue con E10–E23, todas `HECHO` en su fila. E3 conserva su
límite y conviene no leerlo como «probado»: el mecanismo del ejecutor está en código y
protegido por regresiones, pero **no hay corrida operacional con modo real** porque
`skill-gate-run` se abstiene antes de `session/create` al no existir un adaptador
evaluador Host que verifique layout y skill efectiva por caso (`scripts/skill_gate_run.py:604-608`).
Correr el corpus con credenciales propias es una decisión del operador, no un resultado
del framework.

## F1–F6 · Propuestas del borrador de orquestación externa (familia cerrada)

| ID | Propuesta | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| F1 | Specs como artefacto versionado | DECIDIDO históricamente: incorporar trazabilidad, EARS opcional | histórico | `docs/external-orchestration-draft.md` |
| F2 | Cerrar la composición Host real | DECIDIDO históricamente como prioridad del núcleo | histórico | F2 cubierto por C2/C5 |
| F3 | Disparo por evento y delta por push | PENDIENTE / condicionado | histórico | requiere autorización de publicación remota |
| F4 | «1 tarjeta = 1 worktree = 1 agente CLI» | DECIDIDO históricamente: no adoptar | histórico | `docs/external-orchestration-draft.md` |
| F5 | Tres capas de ciclo de vida | Dividida: capa C `HECHO` (E2); capa B `DECLINADO` 2026-10-01 | vivo+histórico | `PLAN_IMPLEMENTACION.md:86`, `:108` |
| F6 | Error concreto del MVP | HECHO (B0) | vivo | `PLAN_IMPLEMENTACION.md:27` |

## G0–G7 · Puertas del plan de lanzamiento (familia cerrada)

| ID | Puerta | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| G0 | Licencia | HECHO 2026-09-30 | vivo | `LICENSE` |
| G1 | `recording_command` emite el JSON exacto | HECHO 2026-09-29 | vivo | `docs/plans/10-lanzamiento-publico.md:31` |
| G2 | `decisions.py`/`metrics.py` dejan de ser huérfanos | HECHO 2026-09-29 | vivo | `docs/plans/10-lanzamiento-publico.md:32` |
| G3 | Desbordamiento de runtime con traza | HECHO 2026-09-29 | vivo | `docs/plans/10-lanzamiento-publico.md:33` |
| G4 | Instalación limpia probada fuera de local | HECHO 2026-09-29 | vivo | `docs/plans/10-lanzamiento-publico.md:34` |
| G5 | Documentación pública | HECHO 2026-09-30 | vivo | `docs/plans/10-lanzamiento-publico.md:35` |
| G6 | Etiqueta y notas | HECHO 2026-09-30 (autorización del titular) | vivo | `docs/plans/11-notas-beta-v0.1.0.md` |
| G7 | Verificación contra el stack real | HECHO 2026-09-29 (26 de 30 stacks sin campaña) | vivo | `docs/plans/10-lanzamiento-publico.md:37` |

G7 conserva el límite que su fila exige publicar como límite: **26 de 30 stacks
siguen declarados sin campaña** (`docs/status.md:250`), no como garantía.

## M1–M9 · Cierre del núcleo MVP v2.4 (RETIRADA del árbol — pasado reutilizado)

`docs/status.md:28-34` declara vigente la eliminación de estos planes; `CHANGELOG.md:786`
registra que el commit `c8aed51` borró los tres documentos históricos. **Ninguna fila es
trabajo vigente**: leerlas como backlog inventaría una obligación.

| ID | Qué fue | Estado derivado | HUS | Acceso |
|---|---|---|---|---|
| M1 | Consumo de cola completa por proyecto | RETIRADO (se consumió en dos proyectos) | histórico | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:22-40` |
| M2 | Reauditoría semántica como turno propio | RETIRADO (validado en piloto DSH real) | histórico | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:41-58` |
| M3 | Controlador Host real | RETIRADO (ciclo mecánico conducido) | histórico | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:59-76` |
| M4 | Aceptación integral por proyecto | RETIRADO (alcanzado con excepciones) | histórico | `git show c8aed51^:docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md:77-83` |
| M5 | Decisiones e instrumentación como servicios | RETIRADO; sus dos servicios siguen en `scripts/` | vivo (servicios) | `scripts/decisions.py`, `scripts/metrics.py` |
| M6 | De «límite documentado» a «probado» | RETIRADO (porción local demostrada) | histórico | `git show c8aed51^:docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md` |
| M7 | `write` rechaza el modo vigente | RESUELTO como plugin | vivo | `scripts/dsh-plugins/anti-escalation.mjs`; P5 |
| M8 | Distribución remota del framework | Distribución RESUELTA 2026-09-13 (clean-room) | vivo | `docs/status.md` |
| M9 | Barrido de esquema sobre la bash real | HECHO en su época (flag M9 dentro de P5) | vivo | P5 |

**Los dos documentos que definían la familia son solo legibles por Git**, y ambos
llevan su propia advertencia de «CONTENIDO HISTÓRICO — NO EJECUTAR».

## P1–P11 · Hardening posterior a C7 (vigente en el índice)

| ID | Unidad | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| P1 | Registro de fuentes y biblioteca materializada | HECHO | vivo | `PLAN_IMPLEMENTACION.md:52` |
| P2 | Integración biblioteca ↔ Creator | HECHO | vivo | `PLAN_IMPLEMENTACION.md:53` |
| P3 | Despacho automático y ciclo de vida DSH | HECHO | vivo | `PLAN_IMPLEMENTACION.md:54` |
| P4 | Sesión Creator ligada al workspace | HECHO | vivo | `PLAN_IMPLEMENTACION.md:55` |
| P5 | Política anti-escalada de sandbox | HECHO | vivo | `PLAN_IMPLEMENTACION.md:56` |
| P6 | Transacción con veredicto Host | HECHO | vivo | `PLAN_IMPLEMENTACION.md:57` |
| P7 | Aceptación Host aislada del Creator | HECHO | vivo | `PLAN_IMPLEMENTACION.md:58` |
| P8 | Instalación de modos como presets DSH | HECHO | vivo | `PLAN_IMPLEMENTACION.md:59` |
| P9 | Gate operativo y ruta real de skills | HECHO | vivo | `PLAN_IMPLEMENTACION.md:60` |
| P10 | Piloto tardis (Syncify) con DSH real | HECHO | vivo | `PLAN_IMPLEMENTACION.md:61` |
| P11 | Gate de holdout para la biblioteca | IMPLEMENTED_NOT_VERIFIED | vivo | `docs/status.md:130` |

**P11 es el límite que más conviene no suavizar:** el gate ligado existe y decide
sobre observaciones verificadas, pero **ningún cambio de biblioteca ha pasado por él
con evidencia de un agente real**. Los 55 casos comprueban 25 skills, no los modos;
el CLI del runner se abstiene antes de crear sesión al faltar un evaluador Host
compatible por caso. La abstención del pase del 2026-10-10 y el `NOT_COVERED` de SC-123
son evidencia de dos límites distintos, no scores de mejora.

## P0–P9 · Fases del plan de ejecución de arquitectura completa (RETIRADA del árbol)

**Aviso de homonimia:** estos `P0`–`P9` no son las once unidades de hardening de
arriba. El identificador `P2` aislado no identifica trabajo sin el documento y la
época. Los dos documentos son legibles solo por Git (`c8aed51`).

| ID | Fase | Estado derivado | HUS |
|---|---|---|---|
| P0 | Reconciliar mandato, inventario y baseline | RETIRADO (ejecutado 2026-09-13) | histórico |
| P1 | Descarga, preparación limpia y bootstrap | RETIRADO (ejecutado) | histórico |
| P2 | Controles Host y composición nativa efectiva | RETIRADO (ejecutado) | histórico |
| P3 | Auditoría completa, requisitos y cobertura | RETIRADO (ejecutado) | histórico |
| P4 | Reparación normal completa y QA independiente | RETIRADO (ejecutado) | histórico |
| P5 | Reauditoría, ledger y cierre | RETIRADO (ejecutado) | histórico |
| P6 | Transición a la arquitectura final | RETIRADO (ejecutado) | histórico |
| P7 | Reemplazo de los modos genéricos | RETIRADO (ejecutado) | histórico |
| P8 | Regresiones y limpieza | RETIRADO (ejecutado) | histórico |
| P9 | UX, métricas, distribución y cierre | RETIRADO; su salida pública es G5 | histórico |

## U1–U6 · Ejecutor de workflows en el Host y campaña por defecto

`U` es la única familia que `PLAN_IMPLEMENTACION.md` **no** recoge como fila: su
sección de estado vive en `docs/status.md:132-157` y su diseño en
`ARQUITECTURA_FLUJO_AGENTES.md:290-300`.

| ID | Unidad | Estado derivado | HUS | Evidencia |
|---|---|---|---|---|
| U1 | Ejecutor de planes sin DSH | HECHO lo probado; Host puro | vivo | `docs/status.md:136`; `scripts/workflow.py`; `tests/test_workflow_executor.py` |
| U2 | Entrada bootstrap y abstención | HECHO lo probado | vivo | `docs/status.md:137`; `tests/test_workflow_bootstrap.py` |
| U3 | Paso `ask` con cliente falso | HECHO con cliente falso, no con DSH real | vivo | `docs/status.md:138`; `tests/test_workflow_ask.py` |
| U4 | Bundle de distribución | PENDIENTE · no ejecutado (requiere autorización) | vivo | `CHANGELOG.md:9`, `:25` |
| U5 | Skill-doctrina en `library/` | PENDIENTE · no ejecutado (gate con sesión real) | vivo | `ARQUITECTURA_FLUJO_AGENTES.md:294` |
| U6 | Campaña de auditoría y reparación por defecto | IMPLEMENTED_NOT_VERIFIED · sin aceptación operativa | vivo | `docs/status.md:4`, `:142`, `:156` |

**U6 acaba de moverse un poco, y conviene ser exacto.** El 2026-10-10 el workflow
mostró, con DSH real, `FAIL → reparación → PASS` en dos runs separados y verificados
(`r-5d7d11…` `RETAINED cause: gate-abort:gate-producto`; `r-7761c0…` `COMPLETED`), y
la invalidación fail-closed de memoria (`MEMORY_RECONCILED`, 6 invalidados). Eso
ejercita el mecanismo, **no** la aceptación operativa: el producto era ficticio y la
campaña no cerra reglas de un repositorio real.

## X1–X3 · Evidencia posterior al pase del 2026-10-10

| ID | Unidad | Estado derivado | Evidencia y límite |
|---|---|---|---|
| X1 | Candidata de reparación sin `worktree` del producto | HOST/SHADOW Y PRESET REAL PROBADOS; ciclo íntegro con preset NO PROBADO | En `x1-live`, un producto ficticio y DSH headless ejercitaron provisión Host fuera del modo, `PROVISIONED → DIRTY`, diff verificado, tests 3/3 y reanudación exacta; el producto quedó intacto. El envoltorio `bwrap` corregido denegó escritura al producto, pero headless no compuso el preset (0 llamadas a `skill`) y dos turnos sumaron 386.441 tokens frente a 250k. En `x1-preset-real`, DSH web resolvió el preset real y cargó su skill, con puerta read-only sobre la sombra del Host; con techo 120.000 el supervisor detuvo la ejecución **antes de editar** por predicción de superarlo (104.372 medidos, 129.898 proyectados; en tanda posterior 97.973 medidos, 127.227 proyectados). **Con techo 200.000 sí llegó a editar**: 11 pasos y 180.107 tokens facturables, la sombra quedó sucia con el defecto canónico reparado (`Math.round(valor)` → `Math.round(valor * 100) / 100`, y el total con IVA redondeado sobre la tarifa ya redondeada), los 3 tests pasaron contra la sombra y el producto canónico quedó intacto; el turno paró por proyección (180.107 medidos, 208.828 proyectados) antes de la segunda reclamación sucia y del cierre `DIRTY`. Falta ese tramo final medido; la edición y los checks ya se ejercieron. Ensayos externos: `x1-live/RESULTADO.md` y `x1-preset-real/RESULTADO.md` |
| X2 | Servidor web y transporte de evaluación | ARRANQUE PROBADO; EVALUADOR HOST AUSENTE | `dsh web` sí arrancó en `0.2.0-rc.2`; el fallo del pase anterior fue el home copiado con `profiles/web/node_modules/` vacío, no un bloqueo actual del arranque. **No existe** un endpoint `evaluator` en esa versión: el gate usa la API real de sesiones (`session/create` + `session/prompt` + `session/page`), pero el CLI no tiene un adaptador evaluador Host compatible que verifique `cwd` por caso y skill efectiva antes de crear sesión (`scripts/skill_gate_run.py:604-608`). Esto es distinto de la generación Creator y del targeting del corpus |
| X3 | Creator y corpus gate contra modo real | CREATOR ACTIVE PRE-PRESUPUESTO; CORPUS NOT_COVERED | Con overlay headless model-facing, Creator generó un manifest `GENERATED` con 19 artefactos y `bootstrap accept`/Host activaron `ACTIVE` (ensayo externo `ensayo-x3-actualizado.md`). **Ocurrió antes del arreglo del budget Creator**; no acredita generación post-budget. En `corpus-fixed`, el frontmatter corregido permitió `skills/list` con 4 skills `modelInvocable` y `skill` reales, y se despachó un caso de 55 (`SC-123`). El gate dio `NOT_COVERED`: el caso compilado apuntaba a la **skill** `source-driven-development`, no al modo `fixture-auditor` que se despachó, y el modo exigió un layout de CWD (`ensayo-x3/fixture/workspace`) que el gate no le dio (sesiona en `case-workspaces/SC-123`), así que `__IMPROVEMENT_LAYOUT_OK__` no salió, el modo narró `RETAINED` sin `workflow_write` y `result.json` no existe. El gate no inventó PASS. Ensayos externos: `corpus-fixed/RESULTADO.md`, `x3-corpus-live/RESULTADO.md` |

## Cómo llegar a la evidencia

- Estado vigente y pisadas del pase real: [docs/status.md](status.md)
- Índice de progreso y deuda: [../PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md)
- Diseño normativo: [../ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md)
- Historial de cambios: [../CHANGELOG.md](../CHANGELOG.md)
- Procedimiento verificado de sesión DSH real: [../skills/dsh-maintenance-session/SKILL.md](../skills/dsh-maintenance-session/SKILL.md)

Nada en este documento convierte una regresión estática en prueba viva: cada fila
`HECHO` lo es por su gate, y cada fila no `HECHO` nombra la pieza que falta.
