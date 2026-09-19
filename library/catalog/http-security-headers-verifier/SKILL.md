---
name: http-security-headers-verifier
description: "Verificar cabeceras de seguridad HTTP distinguiendo lo declarado en código de lo efectivo en el despliegue. Se activa solo con respuestas HTTP observables, cabeceras de seguridad en juego y encargo explícito."
---

# Verificación de cabeceras de seguridad HTTP

## Activación
El patrón solo se selecciona si el proyecto presenta evidencia real:
- frontend o servicio web con configuración de respuestas HTTP observable en el proyecto
- cabeceras de seguridad observadas o encargadas de revisar: CSP, CORS, cookies SameSite, HSTS
- encargo explícito de verificación de cabeceras de seguridad HTTP

Sin esas señales el patrón no aplica; la mera presencia de un servidor web no lo activa.

## Cuándo aplicar
Con las señales de activación presentes: revisar qué cabeceras de seguridad
declara el proyecto y bajo qué condiciones son efectivas.

## Procedimiento
Observa la configuración de cabeceras en el código: middleware, proxy,
framework o manifiesto, con ruta y línea como fuente.
Distingue lo declarado de lo efectivo: una cabecera en código no es una
cabecera servida. Sin evidencia del despliegue real (respuesta capturada
en entorno autorizado o configuración de infraestructura observada),
el resultado es UNVERIFIED.
Evalúa cada cabecera en su contexto: CSP con sus directivas, CORS con sus
orígenes, cookies con SameSite/Secure/HttpOnly, HSTS con su max-age.
Sin conocer proxies intermedios, navegador objetivo y entorno, no se afirma
que una cabecera sea segura: se registra la condición conocida y la faltante.
Cada evaluación cita su fuente: configuración observada o respuesta capturada.

## Invariantes
Lo declarado en código no equivale a lo servido: se exige evidencia de despliegue.
Ninguna afirmación de seguridad sin conocer el contexto de despliegue.
La verificación es de solo lectura: ninguna prueba contra despliegues reales
sin autorización explícita.
Cada cabecera evaluada cita su fuente observable.

## Prohibido y límites
No pruebes despliegues de producción ni de terceros sin autorización propia.
No analices bypass de CSP ni explotación: eso es un encargo de seguridad propio.
No declares "cabecera segura" a partir de la presencia de la cabecera.
Si el despliegue no es observable y no puede autorizarse su observación,
el resultado es NOT_COVERED para la parte efectiva.

## Escenarios y cierre
Escenarios: SC-150 (positiva), SC-151 (segura sin contexto de despliegue),
SC-152 (despliegue no observable).
Entrega: cabeceras declaradas vs efectivas, con fuente y condición conocida.

## Procedencia
Adaptado de mdn-web-docs — instantánea observada de mdn/content
(5a81c288fb7213b2ca2180cda687500981ecf9e1; términos por artefacto, licencia mixta).
Reimplementación propia para este framework, sin copia textual de MDN.
