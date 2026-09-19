---
name: verification-before-completion
description: "Verificar cada criterio de finalización con evidencia externa antes de declarar el trabajo completo. Usar siempre antes de cerrar una unidad; sin criterios declarados, declararlos primero."
---

# Verificación antes de completar

## Cuándo aplicar
Siempre, antes de declarar una unidad o encargo como completo.
Si no hay criterios de finalización declarados, declararlos primero;
"terminado" sin criterios no es un estado válido.

## Procedimiento
Enumera los criterios de finalización: comportamiento esperado, efectos
autorizados, pruebas que deben pasar y evidencia que debe existir.
Por cada criterio, produce evidencia externa: salida de comando, escenario
ejecutado, hash del candidato. La evidencia se cita, no se resume de memoria.
Distingue lo verificado de lo asumido; lo asumido queda como UNVERIFIED
con su causa, no como completado.
Convierte cada duda en una comprobación concreto: una duda razonable sin
comprobación bloquea el cierre, no se disuelve con optimismo.
Declara el estado real: completo con evidencia, parcial con pendientes,
o RETAINED con causa.

## Invariantes
Ningún criterio se marca completo sin evidencia citada y reproducible.
La evidencia corresponde al candidato exacto (hash), no a un estado anterior.
Pendiente declarado no es fallo: ocultarlo sí.
La suite completa cuenta; una suite parcial se declara como parcial.

## Prohibido y límites
No uses "debería funcionar", "en mi máquina pasa" ni resúmenes sin salida.
No cierres con fallos preexistentes presentados como nuevos verdes.
No conviertas un UNVERIFIED en completado por presión de presupuesto.
Si la evidencia requerida no es obtenible, RETAINED con la causa concreta.

## Escenarios y cierre
Escenarios: SC-115 (positiva), SC-116 (negativa: cierre sin evidencia).
Entrega: criterios con evidencia por ítem, pendientes explícitos y estado final.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT)
y de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT,
patrón doubt-driven-development). Reimplementación propia, sin copia textual.
