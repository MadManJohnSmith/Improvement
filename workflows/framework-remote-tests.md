# Workflow: pruebas remotas del framework

**Estado:** especificado a partir del área E (2026-11-06). Cubre el repositorio
del framework, no los proyectos de los usuarios.

## Objetivo

Dejar las comprobaciones del framework corriendo en remoto: la suite
determinista en cada cambio y las evaluaciones de Creator cuando el mantenedor
las pide, con reportes y evidencia reproducibles.

## Disparo

- **Suite determinista:** `push` y `pull_request`.
- **Evaluación de Creator:** `workflow_dispatch` manual, con versión de prompt,
  modelo y presupuesto como entradas.
- Sin horario por defecto.

## Runner

GitHub Actions del repositorio. No hay runner propio ni infraestructura nueva.

## Job 1 — suite determinista

1. Checkout del repositorio.
2. Preparar Python y Node.
3. Ejecutar `python3 -B -m unittest discover -s tests`.
4. Ejecutar los verificadores de plugins
   (`scripts/dsh-plugins/verify-doc-drift.mjs` y
   `scripts/dsh-plugins/verify-workflow-write.mjs`).
5. Publicar el log y el resultado como artifacts del workflow.

Un fallo deja el commit rojo y el flujo publica la prueba que falló y su log. El
mantenedor decide si corrige o revierte; el flujo no repara el repositorio.

## Job 2 — evaluación de Creator

1. Entradas manuales: versión de prompt, modelo y presupuesto.
2. El perfil de DSH del entorno se rellena desde los secretos del repositorio.
   El flujo no fija un proveedor: usa el perfil de DSH disponible en el runner.
3. El producto de prueba es un fixture mínimo y sanitizado en `fixtures/`, con
   identidad y HEAD fijados. Ninguna ruta local del mantenedor entra al flujo.
4. Se ejecuta el caso pre-registrado con `scripts/creator_eval.py` y su conjunto
   cerrado de veredictos (`PASS`, `FAIL_MECHANISM`, `FAIL_COMPLETION`,
   `ABSTAIN`).
5. Se publican el reporte, el roster y los digests como artifacts.

## Checkpoints

- **Fallo de suite:** notificación con la prueba y el log; el mantenedor decide.
- **Reporte de evaluación:** el mantenedor lo revisa y decide el merge. El
  veredicto informa; no es una puerta mecánica. Un `ABSTAIN` por infraestructura
  no bloquea por sí solo.

## Evidencia y secretos

- La suite publica logs y resultados; la evaluación publica reporte, roster,
  journal comprimido y digests.
- El reporte y el roster se versionan solo cuando el mantenedor actualiza el
   roster; no se commitea cada corrida.
- Las claves del proveedor viven en secretos del CI y nunca se imprimen. El
  evaluador registra el modelo usado, no elige proveedor.

## Protocolo de corridas

Acordado el 2026-11-07; la decisión de fondo vive en
`docs/adr/0003-protocolo-de-corridas-remotas.md`. Rige toda corrida
remota del framework.

**Clases.** Una **corrida de sondeo** comprueba infraestructura — que el
cupo del proveedor esté disponible, que el runtime arranque — y espera
`ABSTAIN`: nunca genera fila versionable ni aceptación. Una **corrida de
verificación** es un despacho pre-registrado que busca veredictos
evaluables del caso (y, cuando esté implementado, del recorrido del
producto); es la única que puede terminar en fila versionada. La tarea
automática de reintentos de cupo solo sondea.

**Pre-registro de despacho.** Toda corrida de verificación se anuncia
antes de correrse: comentario en el issue del spec (#11) con las entradas
exactas del despacho (versión de prompt, modelo, presupuesto, fixture,
modo de autenticación) y el SHA de `main` desde el que corre. El agente
de implementación despacha bajo esa regla; el mantenedor puede despachar
sin aviso; la automatización solo sondea.

**Estímulo.** El Creator recibe siempre y solo el prompt que construye el
framework a la versión fijada; su digest queda registrado por run en
`generation-request.json`. Ninguna entrada del workflow altera el texto
del prompt. Los mensajes del usuario simulado nunca entran a la sesión
del Creator.

**Recorrido del producto.** Cuando esté implementado (job posterior a la
calificación del mismo workflow, spec propio posterior a la retro): tras
generar el paquete, un usuario simulado instala, activa (checkpoint 1) y
ejecuta un ciclo real auditoría → reparación → verificación (checkpoint
2). Sus mensajes salen de un guion versionado con una lista versionada de
variaciones que el runner elige de forma determinista: nada se improvisa
dentro de la corrida.

**Reintentos.** Solo el `ABSTAIN` de causa de infraestructura o cupo se
reintenta. Un `FAIL_COMPLETION` o `FAIL_MECHANISM` es evidencia: no se
vuelve a correr sin una versión de prompt nueva.

**Aceptación.** La fila del roster lleva los veredictos de la corrida
(caso y, cuando aplique, los dos checkpoints del recorrido). El workflow
nunca se auto-acepta ni commitea: el mantenedor acepta un caso
versionando su fila tras revisar los artefactos. Un despacho no aceptado
es solo evidencia.

**Corridas locales del agente.** El agente de implementación puede correr
verificaciones locales contra evidencia real solo en modo lectura, con
salidas fuera del repositorio y declaradas en su informe.

## Abierto

- La implementación del job de recorrido del producto (spec propio,
  posterior a la retro).
- Modelo y presupuesto por defecto de la evaluación manual.
- La ventana de cupo anónimo del tier gratuito (hoy bloquea la primera
  corrida completa; los reintentos de sondeo la buscan).
