---
name: writing-plans
description: "Convertir un encargo o diseño en un plan ejecutable por unidades con verificación y presupuesto por unidad. Usar antes de ejecutar trabajo multi-paso; no para tareas de un paso trivial."
---

# Escritura de planes

## Cuándo aplicar
El trabajo necesita más de una unidad o afecta varios archivos.
Aplica tras ideación o discovery, antes de ejecutar.
Tareas de un paso sin efectos no necesitan plan.

## Procedimiento
Descompón el encargo en unidades ordenadas por dependencia real, no por comodidad.
Cada unidad declara: objetivo, archivos que toca, capacidades que necesita,
criterio de verificación observable y presupuesto (intentos, tiempo, tamaño).
Marcar explícitamente qué unidades requieren autorización o QA independiente.
Un plan no se ejecuta a sí mismo: ejecutar es una decisión posterior autorizada.
Si una unidad no puede declarar verificación, divídela o márcala UNVERIFIED.

## Invariantes
El plan es documento: no escribe en el producto ni ejecuta comandos de efecto.
Cada unidad es verificable por sí misma; ningún criterio "funciona en general".
Los efectos de escritura se declaran por unidad; el que ejecuta no amplía alcance.
El plan conserva el orden de dependencias; reordenar exige justificarlo.

## Prohibido y límites
No ejecutar unidades durante la escritura del plan.
No planificar sobre archivos que discovery no observó; marcarlos como hipótesis.
No ocultar unidades riesgosas dentro de otras: cada efecto se lista.
Si el encargo no cabe en unidades verificables, conserva RETAINED con causa.

## Escenarios y cierre
Escenarios: SC-103 (positiva), SC-104 (write-violation).
Entrega: unidades con objetivo/efectos/verificación/presupuesto y orden explícito.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT)
y de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT,
patrón planning-and-task-breakdown). Reimplementación propia, sin copia textual.
