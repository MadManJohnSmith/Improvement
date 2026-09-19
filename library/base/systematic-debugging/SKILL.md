---
name: systematic-debugging
description: "Diagnosticar antes de corregir: reproducir el fallo, formar hipótesis falsables y verificar la corrección contra la reproducción. Usar ante cualquier defecto no trivial; no para cambios cosméticos evidentes."
---

# Depuración sistemática

## Cuándo aplicar
Hay un fallo observado o un comportamiento que contradice el contrato.
Aplica antes de proponer correcciones no triviales.
Un fallo que no se puede reproducir no se corrige a ciegas.

## Procedimiento
Reproduce el fallo con el mínimo caso observable y guarda esa evidencia.
Sin reproducción, declara UNVERIFIED: no apliques correcciones especulativas.
Forma una hipótesis falsable de causa raíz, distinguiéndola del síntoma.
Confirma o refuta con una observación concreta antes de cambiar código.
Aplica un cambio a la vez; cada cambio se justifica por la hipótesis activa.
Verifica la corrección contra la reproducción original y contra regresión
(comprueba que no rompe el comportamiento correcto adyacente).
Si el fallo reaparece, la causa no estaba tratada: vuelve a hipótesis.

## Invariantes
Ninguna corrección sin reproducción observada o causa demostrada.
Un cambio por hipótesis; cambios paralelos impiden atribuir el efecto.
La verificación usa la reproducción guardada, no una versión relajada del caso.
El diagnóstico y los intentos quedan en evidencia, no en memoria.

## Prohibido y límites
No debilites aserciones, tests ni validaciones para que el fallo desaparezca.
No corrijas por síntoma si la causa raíz es alcanzable con la evidencia actual.
No uses reset/stash/clean sobre trabajo activo para limpiar el escenario.
Si el presupuesto de diagnóstico se agota sin causa, RETAINED con lo observado.

## Escenarios y cierre
Escenarios: SC-107 (positiva), SC-108 (negativa: fix sin reproducción).
Entrega: reproducción, causa raíz, corrección verificada y regresión comprobada.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT)
y de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT,
patrón debugging-and-error-recovery). Reimplementación propia, sin copia textual.
