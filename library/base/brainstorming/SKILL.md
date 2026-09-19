---
name: brainstorming
description: "Explorar alternativas antes de comprometer un diseño. Usar cuando un encargo admite varios enfoques y la decisión aún no está justificada; no para ejecutar lo ya decidido."
---

# Ideación con alternativas

## Cuándo aplicar
El encargo admite más de un enfoque y no hay decisión registrada que lo fije.
Si la decisión ya existe y está justificada, no reabrir: ejecutar o retener.
Aplica al diseño de contratos, estructuras, migraciones y enfoques de reparación.

## Procedimiento
Enumera al menos dos alternativas reales antes de recomendar una.
Cada alternativa nombra su fuente de restricción: requisito del encargo, observación
del proyecto con ruta, o constraint declarada. Una opción sin fuente es hipótesis.
Para cada opción anota coste, riesgo y qué evidencia la descartaría.
Descarta con criterio explícito, no por preferencia silenciosa.
Cierra con una recomendación única, las alternativas descartadas y las preguntas
abiertas que el descubrimiento o el diseño deben resolver.

## Invariantes
No implementar durante la ideación: ninguna escritura en el producto.
No ampliar capacidades ni alcance por conveniencia de una opción.
Registrar el porqué de la recomendación; la decisión sin porqué no es evidencia.
Si el encargo ya fija el enfoque, la skill no reabre la decisión.

## Prohibido y límites
No escribir código, tests ni migraciones como parte de idear.
No inventar requisitos del usuario para justificar una opción preferida.
No sustituye discovery: las afirmaciones sobre el proyecto se verifican allí.
Si no hay ninguna alternativa viable con evidencia, conserva RETAINED.

## Escenarios y cierre
Escenarios: SC-101 (positiva), SC-102 (scope-violation).
Entrega: opciones con fuentes, descartes con criterio, recomendación y abiertas.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT).
Reimplementación propia para este framework, sin copia textual.
