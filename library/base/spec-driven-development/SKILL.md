---
name: spec-driven-development
description: "Aceptar una especificación con entradas, salidas, invariantes y anti-goals antes de implementar, y verificar la implementación contra ella. Usar para comportamiento nuevo no trivial; no para erratas sin semántica."
---

# Desarrollo dirigido por especificación

## Cuándo aplicar
Comportamiento nuevo no trivial cuya semántica debe fijarse antes de codificar.
La especificación se registra (documento o contrato del plan); la memoria del
contexto no es especificación.

## Procedimiento
Escribe la especificación: entradas, salidas, invariantes, anti-goals y qué
queda fuera de alcance. Cada elemento observable y verificable.
Confirma la especificación con quien autoriza el encargo antes de implementar;
una spec sin aceptación explícita es propuesta, no contrato.
Implementa contra la spec: cada decisión de diseño se justifica por un punto
de la especificación, no por preferencia.
Si la implementación necesita cambiar la spec, para y re-deriva: se acepta
la nueva spec y se replanifican las unidades afectadas; no se improvisa.
Al cerrar, verifica punto por punto contra la spec, no contra el código.

## Invariantes
La implementación se verifica contra la spec aceptada, no al revés.
Cambios de spec durante ejecución exigen replanificación explícita.
Lo fuera de alcance declarado no se implementa "de paso".
La spec nombra sus fuentes: requisitos del encargo u observaciones del proyecto.

## Prohibido y límites
No implementes comportamiento no trivial sin spec aceptada: RETAINED.
No amplíes la spec silenciosamente mientras codificas.
No uses la implementación como única definición del comportamiento esperado.
No confundas la spec con el plan: la spec fija semántica, el plan fija unidades.

## Escenarios y cierre
Escenarios: SC-119 (positiva), SC-120 (negativa: implementar sin spec aceptada).
Entrega: spec aceptada, trazabilidad decisión→punto de spec, verificación final.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
