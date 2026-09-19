---
name: requesting-code-review
description: "Solicitar revisión independiente con alcance exacto, candidato identificado y camino de verificación. Usar antes de cerrar trabajo de impacto; la revisión no sustituye la aceptación del Host."
---

# Solicitud de revisión

## Cuándo aplicar
El trabajo está completo localmente y su impacto justifica revisión independiente.
El revisor es otro actor distinto del autor; la auto-revisión no es revisión.

## Procedimiento
Define el alcance exacto: archivos y diff identificado con hash del candidato.
Declara qué tipo de feedback se busca: corrección, seguridad, diseño o reglas.
Incluye el camino de verificación: comandos o escenarios que el revisor puede
ejecutar para comprobar el comportamiento sin reconstruir tu contexto.
Añade lo que el revisor no puede saber: decisiones tomadas y porqué, límites
conocidos y qué quedó fuera del alcance deliberadamente.
Divide en revisiones pequeñas cuando el cambio sea grande; revisión enorme
es revisión superficial.

## Invariantes
El candidato revisado queda fijado por hash; feedback sobre otro candidato
no aplica sin reverificación.
El autor no aprueba su propio trabajo; el veredicto lo emite el revisor.
La revisión es consulta al Host: no sustituye acceptance ni validación.

## Prohibido y límites
No enviar a revisión sin verificación local previa (suite en verde, escenarios).
No presentar como candidato un estado distinto del que se revisa.
No marcar revisión como aprobada sin veredicto externo registrado.
Si no hay revisor independiente disponible, conserva UNVERIFIED.

## Escenarios y cierre
Escenarios: SC-111 (positiva), SC-112 (scope-violation).
Entrega: alcance con hash, camino de verificación, decisiones y veredicto externo.

## Procedencia
Adaptado de obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797 (MIT).
Reimplementación propia para este framework, sin copia textual.
