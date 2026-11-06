# Notas de la sesión loop-me — Improvement

## Qué se quiere resolver

No hay acuerdo sobre qué es el framework, qué debe hacer, cómo y en qué orden.
Falta además un flujo de pruebas automatizado que pueda dejarse corriendo en
remoto.

## Mundo y herramientas (hechos)

- Distribución prevista: configurar DSH una vez, clonar el framework y ejecutar
  un bootstrap que coordina Creator, validación Host, respaldo, aceptación,
  activación y rollback de los modos y skills específicos del proyecto.
- DSH 0.2.1 (perfil `web`, presets `standard`/`cordis`), gateway OmniRoute
  local y modelos servidos por OpenRouter.
- Componentes actuales: `bootstrap.py`, Creator (`creator_client.py`, prompt
  1.11.0), `host_validator.py`, modos y skills por proyecto, `workflow.py`
  (gate/join/fase), `creator_eval.py`, `doc-drift`, suite de 1.257 pruebas.
- Estado comprobado: los runs recientes del Creator no produjeron un paquete
  aceptado por el Host. La evaluación de 1.11.0 falló por presupuesto y por
  lecturas del schema de skills.
- Canales: GitHub Issues para specs y tickets; DSH para las sesiones de los
  modos; OmniRoute como puerta de modelos.

## Términos a fijar

- framework, Creator, Host, modo, skill, loop, workflow, trigger, checkpoint,
  brief, aceptación, prueba remota, proyecto usuario, producto de prueba.

## Decisiones del área A (en curso)

- **A1 · Producto primario:** modos por proyecto. Bootstrap, Creator y Host
  entregan y activan `<Proyecto>-auditor`, `<Proyecto>-continuous-repair` y
  `<Proyecto>-implementer`; la responsabilidad del framework termina en la
  activación.
- **A2 · Usuario:** no técnico.
- **A2a · Alcance:** el usuario no técnico también instala. El framework debe
  absorber DSH, el proveedor de modelos y los errores de entorno; la instalación
  es parte del producto, no un paso de desarrollador.
- **A3 · Runtime y modelo:** instalador con DSH incluido y un flujo guiado para
  que el usuario firme con su propia cuenta de OpenRouter u otro proveedor, sin
  terminal ni archivos de configuración. El coste del modelo es del usuario.
- **A4 · Proyecto:** carpeta local elegida en la app; el framework toma la
  instantánea y, si no hay Git, crea el repositorio sombra que necesita.
- **A5 · Interfaz:** la UI de DSH, configurada y abierta por el instalador; los
  modos aparecen como presets. No hay una segunda app de chat.
- **A6 · Éxito:** paquete aceptado y activado más un ciclo real
  auditoría → reparación → verificación, con brief y aprobación, sin escalada ni
  configuración manual. El framework acompaña ese primer ciclo.
- **A7 · Alcance:** modos por proyecto **y** workflows recurrentes arbitrarios;
  no se limita a los tres modos.
- **A8 · Workflows:** el usuario describe el loop en la UI; el framework lo
  compila a `workflows/*.md` con trigger, brief y checkpoint, y el usuario lo
  aprueba antes de ejecutarlo.
- **A9 · Ejecución:** local en el DSH del usuario por defecto; el runner remoto
  —pruebas automatizadas, loops largos— es opcional y se habilita aparte.
- **A10 · Datos:** salen las llamadas al proveedor de modelos y telemetría
  anónima de uso y errores; el proyecto, los journals y la evidencia quedan en
  el equipo salvo que el runner remoto se active.

## Área A — cerrada (2026-11-06)
Identidad: el framework es un instalador y generador de modos por proyecto para
un usuario no técnico que también lo instala, más un compilador de workflows
recurrentes descritos por ese usuario. Se apoya en DSH, usa la cuenta de modelo
del usuario y corre localmente; el éxito es la activación más un ciclo real de
auditoría, reparación y verificación con brief y aprobación. El alcance incluye
telemetría anónima y un runner remoto opcional.

## Mapa de áreas (orden de ataque)

- **A. Identidad y propósito** — qué es, para quién, qué entrega y qué no es.
  Cubre todo: sus respuestas son el criterio con el que se juzgan las demás.
- **B. Entregable y contrato de generación** — bootstrap → Creator → Host →
  aceptación → activación; qué recibe el usuario y dónde termina el framework.
- **C. Flujo y orden operativo** — la secuencia completa, triggers, checkpoints,
  qué corre solo y qué espera al humano.
- **D. Ejecución de los modos** — auditoría, reparación e implementación;
  evidencia, autonomía y aprobación.
- **E. Pruebas y evaluación** — suite, evaluaciones de Creator, automatización
  remota, presupuestos y puertas.
- **F. Distribución y mantenimiento** — instalación, actualización, versionado,
  dependencias (DSH, OmniRoute) y soporte.

Empezamos por A porque fija el criterio de las demás. Después B (el contrato que
materializa A), C (el orden), D (la ejecución), E (las pruebas) y F (la
distribución).

## Decisiones del área B (en curso)

- **B1 · Entrega inicial:** tres modos, sus skills y contratos, manifiesto de
  generación y plan de aceptación. Una sola aprobación del paquete completo; los
  workflows se añaden después por conversación.
- **B2 · Brief:** qué se instalará, qué pueden y qué no pueden hacer los modos,
  qué capas de validación pasaron y la acción siguiente; lenguaje llano y enlace
  al plan, sin JSON crudo.
- **B3 · Fallo:** clasificar la causa (paquete/modelo, proyecto o entorno),
  explicarla en lenguaje llano y reintentar lo que el framework pueda arreglar;
  pedir al usuario solo lo que dependa de él.
- **B4 · Autoridad:** los modos leen, prueban y proponen; escriben hallazgos y
  candidatos en `mode-state`. El producto canónico solo cambia por aceptación
  del Host y aprobación del usuario.
- **B5 · Host:** valida capas deterministas, activa con respaldo y rollback, y
  retiene con causas cuando algo falla.

## Decisiones del área C (en curso)

- **C1 · Primer ciclo:** la primera auditoría arranca sola al activar y termina
  en un brief de hallazgos.
- **C2 · Checkpoints:** dos — aprobar la activación y aprobar la aplicación de
  la reparación. Auditoría y verificación corren solas.
- **C3 · Proyecto sin pruebas:** el Creator propone una suite mínima de conducta
  y la incluye en el paquete; el usuario la aprueba con los modos.
- **C4 · Disparo:** evento primero y ejecución manual; sin horario por defecto.
- **C5 · Modos:** `continuous-repair` se dispara por evento; el resto se usa
  bajo demanda.
- **C6 · Eventos:** prueba fallida y commit nuevo, además del disparo manual.
- **C7 · Orden:** instalar → acceso al proveedor → elegir carpeta → preflight →
  generar → validar → brief → activar → ciclo.
- **C9 · Specs de workflow:** entrevista guiada por rondas, spec revisable y
  aprobación del usuario antes de ejecutar.
- **C12 · Ubicación de specs:** configurable por el usuario; por defecto en el
  producto (`workflows/*.md`), con la escritura autorizada por la aprobación.

## Hecho DSH: cambio de preset

`agentPresets/select` existe en la API instalada, pero el registro solo permite
cambiar el preset mientras la sesión está **en blanco**. Una sesión con turnos
conserva el preset con el que empezó; cambiar de auditor a reparador exige una
sesión nueva. Consecuencia: el flujo entre modos orquesta sesiones nuevas y pasa
el hallazgo/evidencia por `mode-state` o un handoff, no por un cambio in-place.

## Decisiones del área D (en curso)

- **D1 · Roles:** auditor (lee y reporta), reparador (candidato para un
  hallazgo) e implementador (candidato para funcionalidad nueva), separados.
- **D2 · Selección:** el brief de auditoría lista hallazgos; el usuario elige
  cuáles se reparan.
- **D3 · Candidato:** parche y evidencia en `mode-state`; el Host lo aplica a
  una copia sombra, verifica y el usuario aprueba llevarlo al producto.
- **D4 · Autonomía:** presupuesto de tokens y tiempo, con reintentos hasta que
  las pruebas pasan o se agota; si falla, el brief explica por qué.
- **D5 · Implementación:** el usuario la pide en lenguaje natural; el
  implementador pregunta lo que falte y propone candidato, pruebas y brief.
- **D6 · Sesiones:** el framework crea la sesión del rol siguiente con el preset
  correcto y pasa el handoff; el usuario solo aprueba.
- **D7 · Verificación:** el Host aplica el parche a una copia sombra, corre
  pruebas y comprobaciones deterministas, y emite el veredicto sin modelo.
- **D8 · Sesiones conservadas:** cada sesión de rol queda durable y enlazada
  desde el brief; journals y evidencia no se borran.
- **D9 · Rechazo:** el hallazgo sigue abierto, el rechazo queda registrado y el
  usuario puede pedir otro candidato o dejarlo pendiente.

## Decisiones del área E (en curso)

- **E1 · En cada push/PR:** solo la suite determinista; las evaluaciones de
  Creator van aparte.
- **E2 · Runner:** GitHub Actions del repositorio; sin infraestructura propia.
- **E3 · Fallo:** el commit queda rojo y el flujo publica la prueba y el log;
  el mantenedor decide. Sin reparación automática del repo.
- **E4 · Evaluaciones:** workflow manual con versión de prompt, modelo y
  presupuesto; reporte y roster como artefactos.
- **E5 · Merge:** el veredicto informa; el mantenedor decide. Un ABSTAIN de
  infraestructura no bloquea por sí solo.
- **E6 · Alcance remoto:** solo el repositorio del framework; el runner remoto
  de proyectos de usuarios queda como opción posterior.
- **E7 · Producto de prueba:** fixture mínimo y sanitizado en `fixtures/`, con
  identidad y HEAD fijados.
- **E8/8a · Proveedor:** el flujo usa el perfil de DSH del entorno; el CI lo
  rellena con secretos y un runner de usuario usa su cuenta. El evaluador
  registra el modelo, no elige proveedor.
- **E9 · Artefactos:** logs y resultados como artifacts; reporte y roster
  adjuntos. Se versionan solo cuando el mantenedor actualiza el roster.

## Decisiones del área F (cerrada)

- **F1 · Plataformas:** Linux primero; macOS y Windows después, con evidencia
  por plataforma.
- **F2 · Actualizaciones:** la app y DSH se actualizan solos; el paquete se
  regenera con la aprobación de B6.
- **F3 · Telemetría:** aviso en el preflight, con opt-out antes de enviar.
- **F4 · Distribución:** código abierto; cada usuario paga su proveedor.
- **F5 · Soporte:** ayuda dentro de la app y canal de issues.

## Cierre de la sesión loop-me (2026-11-06)

Áreas A–F cubiertas. Las specs están en `workflows/`:
`product-install.md`, `framework-remote-tests.md` y
`user-workflow-design.md`. Las preguntas de implementación que quedan abiertas
están al final de cada spec.
