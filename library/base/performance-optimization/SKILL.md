---
name: performance-optimization
description: "Optimizar con medición: línea base, objetivo declarado y verificación con la misma métrica. Usar solo con evidencia de que el coste actual importa; no micro-optimizar por intuición."
---

# Optimización de rendimiento

## Cuándo aplicar
Existe evidencia de un coste real (medición, usuario, presupuesto) y
el impacto justifica el trabajo. Sin evidencia de coste, la optimización
es especulación: no aplica.

## Procedimiento
Mide la línea base con una métrica definida y reproducible; guarda la salida.
Declara el objetivo numérico y cómo se medirá el resultado con la misma
métrica y condiciones comparables.
Optimiza un factor a la vez; cada cambio se justifica por el modelo del
cuello de botella, no por superstición del lenguaje o del framework.
Re-mide tras cada cambio; lo que no mejora la métrica se revierte
o se justifica por otro criterio explícito (legibilidad, seguridad).
Verifica que la optimización no cambia el comportamiento: la suite
y los escenarios existentes siguen en verde con la misma semántica.

## Invariantes
Ninguna optimización sin línea base medida y objetivo declarado.
Antes y después se miden igual; comparar mediciones distintas no es evidencia.
El comportamiento observado no cambia; solo el coste.
Cada reversión o mantenimiento de un cambio no efectivo queda registrado.

## Prohibido y límites
No optimices sin medición: la intuición no es línea base.
No declares mejora con mediciones no comparables o de un solo intento.
No sacrifiques legibilidad o seguridad sin justificarlo en el registro.
Si el objetivo no se alcanza, declara el resultado real; no lo maquilles.

## Escenarios y cierre
Escenarios: SC-135 (positiva), SC-136 (negativa: optimizar sin línea base).
Entrega: línea base, objetivo, verificación con la misma métrica y comportamiento intacto.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
