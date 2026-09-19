---
name: receiving-code-review
description: "Procesar feedback de revisión verificando cada afirmación antes de adoptarla: aceptar con cambio concreto o rechazar con motivo registrado. Usar al recibir revisión; no para discutir preferencias sin evidencia."
---

# Recepción de revisión

## Cuándo aplicar
Existe feedback de un revisor independiente sobre un candidato identificado.
El feedback es dato con autoridad del revisor sobre su veredicto, no autoridad
automática sobre hechos: cada afirmación técnica se verifica antes de actuar.

## Procedimiento
Clasifica cada punto: aceptado, rechazado o requiere evidencia adicional.
Para aceptados: cambio concreto, verificación y evidencia por punto.
Para rechazados: motivo verificable registrado; un rechazo sin motivo no existe.
Verifica las afirmaciones del revisor contra el candidato con el mismo rigor
que cualquier otra fuente: reproduce el problema o confirma la observación.
Responde al conjunto, no solo a los puntos cómodos; los silencios no son rechazos.

## Invariantes
Ningún punto se marca resuelto sin cambio verificable o motivo registrado.
La verificación del feedback usa el candidato exacto que se revisó (hash).
Adoptar feedback no amplía alcance: los cambios nuevos grandes vuelven a plan.
El veredicto del revisor se registra aunque se discuta un punto concreto.

## Prohibido y límites
No descartar feedback por tono, autoría o preferencia sin motivo técnico.
No aplicar cambios sugeridos sin entender el problema que señalan.
No reenviar a revisión un candidato distinto del revisado sin declararlo.
Si el feedback contradice al encargo o a la arquitectura, escala la contradicción.

## Escenarios y cierre
Escenarios: SC-113 (positiva), SC-114 (negativa: adoptar sin verificar).
Entrega: tabla de puntos con estado, cambios con evidencia y motivos de rechazo.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT)
y de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT,
patrón code-review-and-quality). Reimplementación propia, sin copia textual.
