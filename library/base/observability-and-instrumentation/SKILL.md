---
name: observability-and-instrumentation
description: "Dejar el trabajo diagnosticable: eventos y errores con semántica definida para el comportamiento nuevo. Usar al añadir lógica con estado o efectos; no añadir telemetría por decoración."
---

# Observabilidad e instrumentación

## Cuándo aplicar
Comportamiento nuevo con estado, efectos o fallos posibles: quien opere
después debe poder distinguir qué pasó sin reproducir el turno completo.

## Procedimiento
Para cada comportamiento nuevo, declara cómo se detectaría su fallo:
qué evento, registro o señal lo haría visible y con qué semántica.
Instrumenta los caminos de error con el contexto mínimo para diagnosticar:
identificador de operación, causa y estado; sin ruido ni duplicación.
Nivel de detalle proporcional al impacto; lo crítico es distinguible
de lo normal por contenido, no solo por volumen.
Los registros no contienen secretos ni datos personales; el contenido
sensible se redacta en la fuente, no en el visor.
Verifica la observabilidad como parte del cierre: provoca el fallo
en un ámbito desechable y confirma que la señal aparece.

## Invariantes
Ningún comportamiento nuevo sin camino de diagnóstico declarado.
Cada evento tiene semántica estable: mismo campo, mismo significado.
La evidencia de diagnóstico no filtra secretos ni datos personales.
La señal se comprueba observándola, no confiando en que existirá.

## Prohibido y límites
No instrumentes por decoración: cada señal tiene consumidor y uso.
No uses logs como sustituto de tests ni de evidencia de aceptación.
No registres el contenido completo de entradas no confiables sin límite.
Si el fallo no es observable con las herramientas autorizadas, decláralo.

## Escenarios y cierre
Escenarios: SC-131 (positiva), SC-132 (negativa: fallo invisible).
Entrega: señales con semántica, verificación de detección y redacción aplicada.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
