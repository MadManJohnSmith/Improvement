---
name: fastapi-openapi-contract-check
description: "Comprobar los contratos de endpoints de una aplicación FastAPI contra su esquema OpenAPI reproducible, sin modificar el producto ni llamar a servicios reales. Se activa solo con evidencia FastAPI/Pydantic en el proyecto."
---

# Comprobación de contratos FastAPI vía OpenAPI

## Activación
El patrón solo se selecciona si el proyecto presenta evidencia real:
- fastapi o pydantic declarados en pyproject.toml, requirements o lockfile del proyecto
- routers de FastAPI, modelos BaseModel o documento OpenAPI observados en el proyecto
- encargo explícito de verificar compatibilidad de endpoints o contratos de API

Sin esas señales el patrón no aplica; la mera presencia de Python o de APIs
REST genéricas no lo activa.

## Cuándo aplicar
Con las señales de activación presentes y una tarea de contratos: compatibilidad
de endpoints entre versiones, deriva entre esquema y código, o revisión de
campos, tipos y códigos de error declarados.

## Procedimiento
Fija las versiones exactas en observación: Python, FastAPI y Pydantic
(v1/v2 son materialmente distintas; sin versión, el resultado es UNVERIFIED).
Obtén o reproduce el esquema OpenAPI en un ámbito desechable sin modificar
el producto; si el esquema no es reproducible, el resultado es NOT_COVERED,
no una aproximación.
Compara el contrato observado contra la referencia: rutas, métodos, campos
obligatorios, tipos, valores por defecto y códigos de error.
Clasifica cada diferencia: compatible (aditiva), breaking (rompe consumidores)
o ambigua. Una diferencia sin clasificación no se reporta como verdicto.
Cada hallazgo cita su fuente: ruta y línea del código, o sección del esquema.

## Invariantes
La comprobación es de solo lectura sobre el producto; nunca lo modifica.
Sin llamadas a servicios reales por defecto; toda conexión exige autorización
explícita y ámbito propio.
El esquema OpenAPI debe ser reproducible en la versión fijada observada.
Nada de seguridad se infiere del esquema: auth, idempotencia y autorización
no son visibles en OpenAPI y no se afirman.

## Prohibido y límites
No llames a endpoints reales ni ejecutes el servidor del producto en esta
comprobación; el runtime es otra fase con su propia autorización.
No declares compatibilidad global: el resultado es el inventario de
diferencias clasificadas, no un sello de conformidad.
No actives el patrón sin las señales de activación, aunque "parezca aplicable".
Si la tarea exige ejecución real o carga, retén y escala: este patrón no la cubre.

## Escenarios y cierre
Escenarios: SC-143 (positiva), SC-144 (activación sin evidencia),
SC-145 (capability-denial: llamada a servicio real), SC-146 (esquema no
reproducible).
Entrega: versiones fijadas, inventario de diferencias clasificadas con fuente
y estado (diferencias ≠ defectos declarados).

## Procedencia
Adaptado de fastapi-framework@50113da16fec53b66b80d75e80a89296de4fa5a5 (MIT)
y de pydantic-framework@915896d163835a57fd7987180087409a3229bd71 (MIT).
Reimplementación propia para este framework, sin copia textual.
