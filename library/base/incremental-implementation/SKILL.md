---
name: incremental-implementation
description: "Implementar en incrementos pequeños y verificables, cada uno con su integración comprobada. Usar en cualquier trabajo de implementación mayor que un cambio de una línea; prohibido el big-bang."
---

# Implementación incremental

## Cuándo aplicar
Implementación mayor que un cambio trivial: cada incremento debe dejar
el sistema coherente y verificable por sí mismo.

## Procedimiento
Divide la implementación en incrementos que terminen en un estado
coherente: nada queda a medias entre incrementos.
Cada incremento se verifica al cerrarlo (tests, escenario o comprobación
declarada) antes de abrir el siguiente.
Los puntos de integración se comprueban por incremento, no solo al final:
dos incrementos verdes por separado pueden no componer.
El tamaño del incremento lo fija la verificabilidad, no el volumen:
si no cabe la verificación, divide.
La desviación descubierta a mitad se registra y replanifica; no se
absorbe silenciosamente agrandando el incremento actual.

## Invariantes
Tras cada incremento el sistema está en estado coherente y verificable.
La composición de incrementos se verifica, no se asume.
Ningún incremento mezcla feature nueva con refactor sin declararlo.
El trabajo en curso se describe con su estado real, no como completo.

## Prohibido y límites
No acumules un gran cambio sin verificación intermedia.
No verifiques solo al final: el big-bang es el fallo, no el método.
No avances al siguiente incremento con el actual en rojo sin registrarlo.
Si el encargo solo tiene sentido como big-bang, escala la contradicción.

## Escenarios y cierre
Escenarios: SC-137 (positiva), SC-138 (negativa: integración solo al final).
Entrega: incrementos con verificación propia y composición comprobada.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
