---
name: finishing-a-development-branch
description: "Cerrar una rama de trabajo con checklist de finalización y mutaciones de Git solo por la vía autorizada por el Host. Usar al completar una unidad integrada; nunca para forzar merges o limpiar trabajo ajeno."
---

# Cierre de rama de desarrollo

## Cuándo aplicar
La unidad de la rama está completa y verificada, y procede integrar o cerrar.
Si la rama contiene trabajo ajeno o no verificado, no se cierra: se señala.

## Procedimiento
Ejecuta el checklist de cierre: suite completa en verde, revisión independiente
con veredicto, documentación y evidencia actualizadas, sin cambios sin commitear.
Elabora el resumen de la rama: qué cambia, qué riesgos introduce y qué rollback
aplica si la integración falla.
Toda mutación de Git (commit, merge, push, branch cleanup) se ejecuta solo por
la vía autorizada por el Host (plugin workflow-write o comando autorizado).
Nunca directamente por la skill.
Tras la integración, verifica el estado resultante: hashes y rama esperada.
Si el cierre requiere descartar algo, exige autorización explícita y registra
qué se descarta y porqué.

## Invariantes
Nada se integra sin checklist completo; el pendiente se declara, no se asume.
Las mutaciones de Git usan la vía autorizada; la skill no tiene autoridad propia.
El rollback queda definido antes de integrar, no después del fallo.
El trabajo ajeno detectado se señala; no se descarta ni se incluye en silencio.

## Prohibido y límites
No fuerces push, reset --hard ni limpieza sobre trabajo activo o ajeno.
No cierres la rama con la suite en rojo ni con verificación parcial sin declararlo.
No reescribas historial compartido sin autorización explícita del titular.
Si la vía autorizada no está disponible, RETAINED: sin atajos por shell.

## Escenarios y cierre
Escenarios: SC-117 (positiva), SC-118 (write-violation).
Entrega: checklist completo, resumen con rollback, integración verificada.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT).
Reimplementación propia para este framework; las mutaciones de Git quedan
en el plugin workflow-write y el Host, sin autoridad propia de la skill.
