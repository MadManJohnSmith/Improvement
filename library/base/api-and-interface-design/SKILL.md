---
name: api-and-interface-design
description: "Diseñar interfaces y contratos antes del detalle: entradas, salidas, errores y compatibilidad con consumidores. Usar al exponer o modificar límites de módulos, servicios o APIs públicas."
---

# Diseño de interfaces y contratos

## Cuándo aplicar
Al crear o modificar el límite visible de algo: función pública, módulo,
API, esquema o mensaje. El detalle interno no exige esta skill.

## Procedimiento
Define el contrato primero: entradas con tipos y rangos, salidas, errores
posibles con su semántica y casos de fallo declarados.
Inventario de consumidores actuales del contrato antes de cambiarlo;
cada consumidor identificado con ruta o referencia verificada.
Los cambios incompatibles se declaran como breaking: versión, migración
y anuncio; nunca pasan como cambio interno.
Diseña el fallo como parte del contrato: qué se garantiza cuando algo falla.
El mínimo superficie posible: todo elemento expuesto es un compromiso
de mantenimiento; lo que no hace falta, no se publica.

## Invariantes
Ningún cambio de contrato sin inventario de consumidores verificado.
Los errores tienen semántica declarada, no son excepciones anónimas.
La compatibilidad se verifica, no se supone por similitud de nombres.
El contrato queda registrado y visible antes de la implementación.

## Prohibido y límites
No cambies semántica de un contrato manteniendo la firma.
No expongas internos por comodidad de la implementación.
No declares compatibilidad sin haber comprobado a los consumidores.
Si el consumidor real no es observable, el cambio se marca UNVERIFIED.

## Escenarios y cierre
Escenarios: SC-129 (positiva), SC-130 (negativa: ruptura sin inventario).
Entrega: contrato con errores, inventario de consumidores y política de versión.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
