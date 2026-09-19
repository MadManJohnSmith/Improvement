---
name: executing-plans
description: "Ejecutar un plan por unidades con checkpoint tras cada una y reanudación idempotente. Usar con un plan existente y autorización de ejecución; nunca para modificar el plan en silencio."
---

# Ejecución de planes

## Cuándo aplicar
Existe un plan con unidades declaradas y hay autorización de ejecución.
Sin plan previo, volver a writing-plans; sin autorización, retener.

## Procedimiento
Ejecuta una unidad a la vez, dentro de su alcance y presupuesto declarados.
Tras cada unidad, checkpoint: evidencia de verificación, efectos observados,
estado para reanudar. Sin checkpoint no se inicia la siguiente unidad.
Al reanudar tras interrupción, verifica el estado real antes de repetir:
no reescribas a ciegas una unidad cuyo efecto es incierto.
La desviación necesaria no se improvisa: detén, documenta la causa y
replanifica la unidad o conserva la unidad en RETAINED.

## Invariantes
El alcance de ejecución es el del plan; ampliarlo exige volver al plan.
Reanudación idempotente: reintentar nunca duplica efectos ni corrompe estado.
Cada unidad cierra con evidencia externa, no con la afirmación de que funcionó.
El presupuesto agotado suspende la unidad; no se recupera ampliando límites.

## Prohibido y límites
No editar el plan durante la ejecución para que una unidad pase.
No ejecutar unidades fuera de orden si el plan declara dependencias.
No repetir escrituras de efecto incierto sin reconciliación previa.
Si dos unidades fallan por la misma causa, detén y escala la causa,
no sigas consumiendo presupuesto por unidad.

## Escenarios y cierre
Escenarios: SC-105 (positiva), SC-106 (idempotence).
Entrega: por unidad, evidencia de verificación, efectos y estado de reanudación.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT).
Reimplementación propia para este framework, sin copia textual.
