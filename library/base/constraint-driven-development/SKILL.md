---
name: constraint-driven-development
description: "Declarar las restricciones del trabajo por adelantado (presupuesto, archivos permitidos, capacidades prohibidas) y verificar cada unidad contra ellas. Usar siempre que el encargo tenga límites explícitos; no negociar restricciones en silencio."
---

# Desarrollo dirigido por restricciones

## Cuándo aplicar
El encargo declara límites: presupuesto, tiempo, archivos tocables, capacidades
prohibidas, estilo o compatibilidad. Las restricciones se declaran antes de
empezar y se verifican durante, no se recuerdan de oídas.

## Procedimiento
Registra las restricciones en el plan o contrato de la unidad: presupuesto de
intentos/coste, archivos y rutas permitidas, capacidades requeridas y prohibidas.
Cada unidad se verifica contra las restricciones vigentes antes y después:
archivos tocados vs permitidos, efecto vs presupuesto, capacidades vs allowlist.
Una restricción violada detiene la unidad: se registra la violación, se
restaura lo restaurable y se escala la decisión; no se negocia en silencio.
Si una restricción resulta inviable, quien autoriza la relaja por escrito;
el relajamiento queda en evidencia con fecha y motivo.

## Invariantes
Las restricciones viven en el contrato del trabajo, no en la memoria del turno.
Verificar restricciones es parte de la unidad, no un paso opcional final.
La violación registrada detiene; el silencio ante una violación es un fallo.
El presupuesto agotado suspende sin excepciones informales.

## Prohibido y límites
No toques archivos fuera de la lista permitida "porque es necesario".
No amplíes presupuesto ni tiempo sin autorización registrada.
No relajes validaciones para que la unidad quepa en la restricción.
Si dos restricciones del encargo se contradicen, escala antes de elegir.

## Escenarios y cierre
Escenarios: SC-121 (positiva), SC-122 (negativa: violación de restricción).
Entrega: restricciones registradas, verificación por unidad y violaciones con escala.

## Procedencia
Adaptado de addyosmani/agent-skills@be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39
(MIT). Reimplementación propia para este framework, sin copia textual.
