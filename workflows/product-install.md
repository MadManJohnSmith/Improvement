# Workflow: instalación y primer ciclo de un proyecto

**Estado:** especificado a partir de las áreas A–F (2026-11-06). Es la fuente de
verdad de este loop; las decisiones abiertas están al final.

## Objetivo

Llevar a un usuario no técnico desde la instalación de la aplicación hasta el
primer ciclo real de auditoría, reparación y verificación, con los tres modos
del proyecto activados. El éxito es la activación más ese ciclo, no solo el
paquete generado.

## Disparo

- Una vez por proyecto, cuando el usuario instala la aplicación y elige la
  carpeta del proyecto.
- Se repite cuando una versión nueva del framework propone regenerar el paquete
  y el usuario lo aprueba.

## Actores

- **Usuario no técnico:** instala, firma con su cuenta de modelos, elige la
  carpeta, aprueba y decide.
- **Instalador:** incluye DSH, abre su interfaz y guía el acceso al proveedor.
- **Host:** instantánea, preflight, validación determinista, activación,
  respaldo y rollback.
- **Creator:** genera el paquete de modos, skills, contratos, manifiesto y plan
  de aceptación.
- **Modos:** auditor, reparador e implementador, cada uno en su sesión y con su
  techo de autoridad.

## Pasos

1. **Instalar la aplicación.** El instalador incluye DSH y lo deja listo; no se
   pide terminal ni archivos de configuración.
2. **Acceso al proveedor de modelos.** Flujo guiado para que el usuario firme
   con su propia cuenta (OpenRouter u otro proveedor compatible). El coste del
   modelo es del usuario y la clave no se escribe en el repositorio.
3. **Elegir la carpeta del proyecto.** El framework toma una instantánea; si no
   hay Git, crea el repositorio sombra que necesita el Host.
4. **Preflight local.** Detecta lenguaje, pruebas y estado del árbol; muestra el
   aviso de privacidad y telemetría. Si no hay pruebas, el Creator propondrá una
   suite mínima de conducta y el usuario la aprobará con el paquete.
5. **Generar el paquete.** Tres modos, sus skills y contratos, la suite base si
   faltaba, `generation-manifest.json` y el plan de aceptación. Una sola
   aprobación para todo el paquete; los workflows se añaden después.
6. **Validar.** El Host aplica las capas deterministas (schema, manifiesto,
   grafo, contratos, capacidades, portabilidad, presupuesto, colisión, licencia
   y ciclo de vida). Si falla, clasifica la causa —paquete/modelo, proyecto o
   entorno—, la explica en lenguaje llano y reintenta lo que puede arreglar.
7. **Checkpoint 1: aprobar la activación.** El brief dice qué se instalará, qué
   podrán y qué no podrán hacer los modos, qué capas pasaron y la acción
   siguiente; incluye un enlace al plan completo, no JSON crudo.
8. **Activar.** El Host respalda el estado anterior, instala los presets y deja
   el rollback disponible.
9. **Primera auditoría automática.** El framework crea la sesión del auditor y
   presenta un brief de hallazgos con severidad y evidencia.
10. **El usuario elige los hallazgos.** Del brief, elige uno o varios; el
    framework crea una sesión nueva del reparador (el preset no cambia dentro de
    una sesión con turnos) y le pasa el handoff del hallazgo y su evidencia.
11. **Reparación.** El reparador escribe un parche y la evidencia en
    `mode-state`, con presupuesto de tokens y tiempo y reintentos hasta que las
    pruebas pasan o el presupuesto se agota. El Host aplica el parche a una
    copia sombra, corre las pruebas y las comprobaciones deterministas.
12. **Checkpoint 2: aprobar la aplicación.** El brief muestra el diff, las
    pruebas y la evidencia. Si el usuario aprueba, el Host lleva el cambio al
    producto. Si rechaza, el hallazgo sigue abierto y puede pedir otro candidato,
    elegir otro hallazgo o dejarlo pendiente.
13. **Cierre.** Los modos quedan disponibles; `continuous-repair` queda armado
    para prueba fallida y commit nuevo, además del disparo manual. Las sesiones
    de cada rol se conservan y se enlazan desde el brief.

## Checkpoints

- **Activación:** una sola aprobación del paquete completo.
- **Aplicación de la reparación:** una aprobación del candidato verificado. La
  auditoría y la verificación no piden aprobación.

## Briefs

- **De activación:** qué se instala, techo de autoridad, validaciones pasadas,
  acción siguiente y enlace al plan.
- **De hallazgos:** lista priorizada con severidad, ubicación y evidencia.
- **De reparación:** diff, pruebas, evidencia y consecuencia de aprobar o
  rechazar.

## Rutas de fallo

- **Paquete o modelo:** diagnóstico, explicación y reintento guiado.
- **Entorno:** repetir el acceso al proveedor o el arranque de DSH.
- **Proyecto:** pedir solo lo que depende del usuario; si faltan pruebas, el
  Creator propone la suite base.
- **Reparación agotada:** brief con la causa y opciones —más presupuesto, otro
  enfoque o dejar el hallazgo abierto—; nunca un fallo silencioso.

## Autoridad y datos

- Los modos leen, prueban y proponen; escriben hallazgos y candidatos en
  `mode-state`. El producto canónico solo cambia por el Host y con la aprobación
  del usuario.
- Salen del equipo las llamadas al proveedor de modelos y la telemetría anónima
  de uso y errores; el proyecto, los journals y la evidencia quedan locales
  salvo que se active el runner remoto opcional.
- La ejecución es local por defecto. El runner remoto de proyectos es una opción
  posterior, no parte de este loop.

## Distribución y actualizaciones

- Primera versión en Linux; macOS y Windows después, con evidencia por
  plataforma.
- Código abierto; cada usuario paga su proveedor de modelos.
- La app y DSH se actualizan solos; el paquete se regenera con la aprobación de
  B6.
- Telemetría: aviso en el preflight, con opt-out antes de enviar.
- Ayuda dentro de la app y canal de issues.

## Abierto

- Mecánica fina del rollback entre versiones del framework.
- Formato exacto del instalador en Linux y su empaquetado.
