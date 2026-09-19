---
name: web-accessibility-wcag-audit
description: "Auditar la accesibilidad de un frontend contra WCAG 2.2 con nivel objetivo declarado, separando pruebas automáticas de revisión manual. Se activa solo con frontend web, nivel A/AA/AAA declarado y encargo de accesibilidad."
---

# Auditoría de accesibilidad WCAG 2.2

## Activación
El patrón solo se selecciona si el proyecto presenta evidencia real:
- frontend web con HTML, CSS o ARIA observado en el proyecto
- objetivo WCAG declarado (nivel A, AA o AAA) en el encargo o en la configuración del proyecto
- encargo explícito de auditoría de accesibilidad web

Sin esas señales el patrón no aplica; una página web genérica no lo activa.

## Cuándo aplicar
Con las señales de activación presentes y un nivel objetivo declarado:
auditar criterios de WCAG 2.2 sobre las rutas e interfaces del proyecto.

## Procedimiento
Fija el nivel objetivo (A, AA o AAA) antes de auditar; sin nivel declarado
el resultado es UNVERIFIED, no una auditoría genérica.
Ejecuta las comprobaciones automáticas autorizadas sobre las rutas observadas
y registra qué criterios cubren; las herramientas automáticas cubren un
subconjunto y nunca declaran conformidad por sí solas.
La revisión manual de teclado y lector de pantalla es requisito para afirmar
conformidad: sin ella, el resultado es PARTIAL o UNVERIFIED, con lo que falta.
Por cada criterio evaluado registra: criterio WCAG, nivel, evidencia
(captura, salida de herramienta o nota de revisión manual) y resultado.
El contraste y el render dependen del entorno real: declara la condición
en la que se verificó y qué quedó fuera de ella.

## Invariantes
Ningún resultado sin nivel objetivo declarado.
Las pruebas automáticas no declaran conformidad: solo cubren un subconjunto.
La conformidad exige revisión manual de teclado y lector de pantalla.
La auditoría es de solo lectura sobre el producto.

## Prohibido y límites
No declares "sitio accesible" ni conformidad certificada: el resultado es
evidencia por criterio, no un sello.
No uses la puntuación de una herramienta (Lighthouse o equivalente) como
veredicto de conformidad.
No audites rutas que no observaste; márcalas como no cubiertas.
Si el nivel objetivo no puede declararse, retén hasta que se declare.

## Escenarios y cierre
Escenarios: SC-147 (positiva), SC-148 (conformidad solo por herramienta),
SC-149 (auditoría sin nivel declarado).
Entrega: nivel objetivo, criterios con evidencia y resultado, y lo no cubierto.

## Procedencia
Adaptado de wcag-22 — WCAG 2.2, W3C Recommendation publicada el 2024-12-12
(licencia W3C document, abierta con condiciones de atribución).
Reimplementación propia para este framework, sin copia textual del estándar.
