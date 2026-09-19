---
name: test-driven-development
description: "Fijar el comportamiento esperado en un test que falla antes de implementar, y verificar contra ese test. Usar para lógica nueva o correcciones con comportamiento verificable; no para prototipos desechables declarados."
---

# Desarrollo dirigido por tests

## Cuándo aplicar
Comportamiento nuevo o corrección con resultado verificable.
Exige herramienta de tests autorizada en el proyecto; si no la hay,
conserva RETAINED: no se sustituye con impresiones ni revisión manual.

## Procedimiento
Escribe primero el test que expresa el comportamiento esperado y ejecútalo:
debe fallar por la razón correcta (aserción, no import error ni fixture roto).
Implementa lo mínimo para volverlo verde; el test no se modifica para pasar.
Refactoriza con los tests en verde; cada refactor mantiene verde la suite.
En correcciones, el test nuevo reproduce el defecto antes del fix.
Si el test no puede fallar, no está probando el comportamiento: reescríbelo.

## Invariantes
Rojo observado antes de implementar; verde observado después; ambos con salida.
Los tests viajan con el comportamiento: sin test, el comportamiento no está fijado.
No se debilita una aserción para lograr verde; eso es un fallo nuevo, no un pase.
La suite existente se ejecuta antes de declarar verde local.

## Prohibido y límites
No escribas el test después adaptándolo a la implementación ya hecha.
No simules cobertura con tests triviales que no pueden fallar.
No marques verde con ejecuciones parciales de la suite sin declararlo.
Para prototipos desechables declarados, la skill no aplica: márcalo explícito.

## Escenarios y cierre
Escenarios: SC-109 (positiva), SC-110 (negativa: implementar sin rojo observado).
Entrega: test, evidencia de rojo, implementación mínima y verde con suite completa.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT)
y de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT).
Reimplementación propia para este framework, sin copia textual.
