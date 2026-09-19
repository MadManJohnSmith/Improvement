---
name: code-simplification
description: "Reducir complejidad sin cambiar el comportamiento, protegido por tests y como unidad separada. Usar cuando la deuda de claridad ya cuesta; no mezclar simplificación con features."
---

# Simplificación de código

## Cuándo aplicar
La complejidad observada ya produce coste: errores de mantenimiento,
revisiones lentas, duplicación que diverge. Es una unidad propia,
no un subproducto de otra tarea.

## Procedimiento
Fija primero la red de seguridad: tests y escenarios que cubren el
comportamiento actual; sin ellos, la simplificación no empieza.
Identifica el objetivo concreto: duplicación que diverge, abstracción
sin segundo caso de uso, rama muerta verificada, indirección inútil.
Simplifica en pasos verificables, cada uno con la suite en verde;
un paso sin verde se revierte, no se "termina de arreglar" después.
La eliminación de código exige evidencia de que está muerto: referencias
comprobadas, no sospecha. Una referencia dinámica posible bloquea el borrado.
Al cerrar, verifica el comportamiento observable: mismo contrato,
menos mecanismo.

## Invariantes
El comportamiento observable no cambia; la suite es la prueba.
Simplificación y feature nunca viajan en la misma unidad.
Nada se borra sin evidencia de que está muerto.
Cada paso de simplificación es reversible y atribuible.

## Prohibido y límites
No cambies el contrato público "de paso" mientras simplificas.
No introduzcas una abstracción nueva para justificar la simplificación.
No simplifiques lo que no comprendes: primero diagnóstico, luego edición.
Si la red de seguridad no puede autorizarse, RETAINED con causa.

## Escenarios y cierre
Escenarios: SC-139 (positiva), SC-140 (negativa: cambio de comportamiento).
Entrega: red de seguridad verificada, pasos con verde y comportamiento intacto.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
