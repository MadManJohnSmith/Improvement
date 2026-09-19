---
name: documentation-and-adrs
description: "Registrar las decisiones con su contexto, alternativas y consecuencias, y mantener la documentación al día con el comportamiento. Usar al tomar decisiones no triviales o cambiar comportamiento documentado."
---

# Documentación y registros de decisión

## Cuándo aplicar
Al tomar una decisión no trivial que otro actor necesitará entender
(estructura, dependencia, convención, trade-off), y al cambiar
comportamiento que está documentado.

## Procedimiento
Registra cada decisión no trivial con: contexto que la motiva, alternativas
consideradas con su descarte, consecuencia esperada y fecha/autoría.
Sigue la convención de registro del proyecto; si no existe, una por decisión,
numerada y en el lugar acordado, no dispersa en el historial de chat.
Actualiza la documentación afectada en la misma unidad que el cambio:
documentación contradicha por el código es un defecto, no un pendiente.
La documentación describe el comportamiento observado, con ejemplos
ejecutables cuando el contrato lo permita.
Referencias a fuentes y decisiones previas por su registro, no de memoria.

## Invariantes
Una decisión sin alternativas consideradas no está registrada: es una anécdota.
El cambio de comportamiento y su documentación viajan juntos.
Los registros son append-only: corregir es añadir una nueva entrada
que referencia a la anterior, no reescribirla en silencio.
La documentación afirma solo lo verificable contra el código actual.

## Prohibido y límites
No documentes aspiraciones como si fueran comportamiento.
No dupliques contratos en prosa; referencia la fuente única.
No dejes la documentación "para el final" de un encargo grande.
Si no puedes actualizar la documentación en esta unidad, el pendiente
queda declarado en el cierre, no oculto.

## Escenarios y cierre
Escenarios: SC-133 (positiva), SC-134 (negativa: decisión sin contexto).
Entrega: registros con alternativas y consecuencias; documentación al día.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
