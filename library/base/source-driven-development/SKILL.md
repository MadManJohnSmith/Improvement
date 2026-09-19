---
name: source-driven-development
description: "Nombrar una fuente verificable para cada afirmación operativa y marcar como hipótesis lo no verificado. Usar en cualquier análisis, auditoría o diseño; una afirmación sin fuente no es evidencia."
---

# Desarrollo dirigido por fuentes

## Cuándo aplicar
En todo análisis, auditoría, diseño o informe: cada afirmación operativa sobre
el proyecto o el comportamiento debe nombrar de dónde sale.
Una afirmación sin fuente es hipótesis: puede guiar la exploración,
no puede sustentar una decisión.

## Procedimiento
Cada afirmación lleva fuente: ruta y línea observada, salida de comando,
documento con versión/commit o decisión registrada.
Distingue OBSERVED (verificado ahora, con evidencia) de INFERRED (deducido)
y ASSUMED (sin verificación). Solo OBSERVED sustenta cierres y veredictos.
Las hipótesis que guían el trabajo se listan como tales y se convierten
en comprobaciones; al verificarse cambian de estado, no de etiqueta retórica.
Cuando dos fuentes se contradicen, registra la contradicción y resuélvela
con la fuente de mayor autoridad declarada; nunca promediando silenciosamente.

## Invariantes
Ninguna afirmación en informes, manifests o veredictos sin fuente citada.
El estado de la afirmación (OBSERVED/INFERRED/ASSUMED) se declara junto a ella.
La fuente se verifica en el momento; una fuente vieja se re-verifica antes
de reutilizarla si el objeto pudo cambiar.
La ausencia de fuente retiene la decisión: no hay inferencia silenciosa.

## Prohibido y límites
No cites como fuente algo que no observaste en esta ejecución sin marcarlo.
No conviertas una suposición repetida en observación por repetición.
No uses el nombre de una herramienta como fuente: la fuente es su salida.
Si el encargo exige afirmaciones sin fuente posible, decláralo y retén.

## Escenarios y cierre
Escenarios: SC-123 (positiva), SC-124 (negativa: afirmación sin fuente).
Entrega: afirmaciones con fuente y estado, contradicciones resueltas con autoridad.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT, patrón source-driven-development). Reimplementación propia para este
framework, alineada con value sourcing de la arquitectura, sin copia textual.
