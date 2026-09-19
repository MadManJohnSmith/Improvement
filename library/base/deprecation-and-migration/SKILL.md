---
name: deprecation-and-migration
description: "Retirar o sustituir un contrato con ventana de deprecación, migración documentada y rollback. Usar al eliminar o reemplazar APIs, esquemas o flujos con consumidores; nunca un borrado directo."
---

# Deprecación y migración

## Cuándo aplicar
Un contrato (API, esquema, flujo, campo) va a retirarse o sustituirse
y existen o pueden existir consumidores. Sin ventana ni migración,
no hay retirada: hay rotura.

## Procedimiento
Declara la deprecación: qué se deprecia, desde cuándo, cuál es el
reemplazo y cuándo se prevé retirar. El anuncio es parte del cambio.
Ofrece el camino de migración: pasos ejecutables documentados y,
si procede, herramienta de transición verificada.
Durante la ventana, el comportamiento deprecado sigue funcionando
y señala su estado; el nuevo y el viejo no divergen silenciosamente.
La retirada exige evidencia de que no quedan consumidores: inventario
verificado en el momento, no el del último recuerdo.
Define el rollback antes de migrar: cómo se vuelve al estado previo
si la migración falla a mitad.

## Invariantes
Ninguna retirada sin ventana declarada y consumidor final verificado.
La migración es reversible o se declara irreversible con autorización.
Durante la ventana, viejo y nuevo conviven con semántica declarada.
Cada paso de migración verifica la conservación de datos y comportamiento.

## Prohibido y límites
No borres contratos con consumidores posibles sin inventario verificado.
No mezcles la migración con cambios de semántica no anunciados.
No declares migración completa sin evidencia de conservación.
Si el inventario de consumidores no es observable, la retirada es UNVERIFIED.

## Escenarios y cierre
Escenarios: SC-141 (positiva), SC-142 (negativa: borrado sin ventana).
Entrega: ventana declarada, migración verificada, retirada con inventario y rollback.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
