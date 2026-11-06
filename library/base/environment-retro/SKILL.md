---
name: environment-retro
description: "Convertir fallos observados de una sesión en cambios del entorno: check automático para fallos mecánicos, standard para judgement calls y hallazgo para guardrails ausentes. Usar al cerrar una unidad; no para reescribir el producto."
---

# Retro de entorno: de fallos de sesión a cambios del entorno

## Cuándo aplicar
Una sesión o unidad cerró —COMPLETED, RETAINED o BLOCKED— y existe evidencia persistida de
fallos: episodios, hallazgos del ciclo, journal o veredictos del Host. Aplica al cierre de
cada unidad con fallos que un cambio del entorno habría evitado. No aplica a producto sin
sesión: sin evidencia no hay retro.

## Procedimiento
Recolecta los fallos anclados a su evidencia: ruta, línea o recibo. La narración de la
sesión no es evidencia por sí sola.
Clasifica cada fallo con su regla: fallo mecánico → propuesta de check automático;
judgement call recurrente → standard declarado; guardrail ausente → hallazgo registrado.
Propón el cambio del entorno con su verificación: el check nuevo llega con un test que
falla sin él; el standard llega con su criterio de aplicación.
Registra qué fallo origina cada cambio y qué evidencia lo respalda.
Cierra con la lista de cambios propuestos, los fallos que la motivan y lo que queda abierto.

## Invariantes
Un fallo mecánico produce una propuesta de check automático, no una instrucción nueva.
Un judgement call produce un standard, nunca un check que finge objetividad.
Un guardrail ausente se registra como hallazgo, no se improvisa.
El retro jamás edita el producto: ni código, ni tests, ni estado.
Cada propuesta está anclada a evidencia de sesión persistida.

## Prohibido y límites
No reescribir código, tests ni estado del producto como parte del retro.
No inventar fallos que la evidencia de la sesión no contiene.
No acoplarse a un harness concreto: el entorno es el del proyecto, no el del agente.
Sin evidencia de sesión persistida, no hay retro: conserva RETAINED.

## Escenarios y cierre
Escenarios: SC-158 (positiva), SC-159 (negative).
Entrega: fallos anclados, clasificación por regla, cambios de entorno propuestos con su
verificación y abiertas.

## Procedencia
Reimplementación propia de la capacidad `retro` de
mattpocock/skills@49dd158d1076134a641b33efb035946536778336 (MIT); sin copia de texto. La
regla de clasificación mechanical→deterministic / judgement→standard procede del patrón
adaptado.
