---
name: shipping-and-launch
description: "Preparar una salida verificable: plan de rollback declarado antes de desplegar, rollout por etapas con señales y error budget. Usar cuando un cambio verificado va a producción; no para ejecutar el despliegue."
---

# Salida y lanzamiento con rollback declarado

## Cuándo aplicar
Existe un cambio acabado y verificado que va a salir del workspace hacia un entorno donde
un fallo tiene coste real. Aplica a despliegues, migraciones con ventana y cambios de
configuración compartida. No aplica a cambios que no salen del repositorio: ahí basta la
verificación del ciclo normal.

## Procedimiento
Declara el plan de rollback antes de proponer la salida: qué se revierte, con qué pasos y
cómo se comprueba que la reversión funcionó.
Define las etapas del rollout y, para cada avance, la señal observable que lo autoriza y el
umbral que lo detiene. Una etapa sin señal no avanza.
Consulta el error budget del servicio. Agotado, no hay avance: se congela o se revierte.
Nombra la candidata exacta que se propone (sha o digest) y el artefacto que se despliega.
Cierra con la decisión propuesta al operador: avanzar, mantener o revertir.

## Invariantes
Sin plan de rollback declarado no existe propuesta de salida.
El rollout avanza solo con señales declaradas; señal ausente se trata como hold.
Error budget agotado impide avanzar, con independencia de la prisa del encargo.
El registro de salida nombra la candidata exacta y sus digests.
La skill no despliega: propone el plan y el operador ejecuta.

## Prohibido y límites
No ejecutar despliegues, migraciones ni cambios de infraestructura.
No inventar señales de salud ni dar por hecho que la suite verde equivale a salud en
producción.
No declarar un rollback «manual» sin pasos verificables: un rollback que nadie sabe
ejecutar no es un plan.
Sin evidencia del proyecto sobre el entorno de salida, conserva RETAINED.

## Escenarios y cierre
Escenarios: SC-156 (positiva), SC-157 (negative).
Entrega: plan de rollback, etapas con señales, estado del error budget, candidata exacta y
decisión propuesta.

## Procedencia
Reimplementación propia de la capacidad de `shipping-and-launch` de
addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39 (MIT); sin copia de texto.
La autoridad de ejecución permanece en el operador y en el Host.
