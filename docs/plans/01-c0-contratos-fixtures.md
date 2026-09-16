# Plan 01 — C0: contratos, schemas y fixtures

**Salida:** corpus de contratos versionados y fixtures válidos/negativos para validar C1–C5.
**Precondiciones:** arquitectura 3.0, runtime observado y servicios Host MVP disponibles.

## Artefactos

- schemas de `run`, `project-manifest`, `instructions-index`, `capabilities`, `generation-manifest`, `modes`, `skills`, `scenario`, `handoff`, `drift`, `backup`, `promotion`, `rollback`;
- schema de biblioteca base inmutable, catálogo de patrones, composición, override limitado, transferencia y extensión;
- aplicabilidad, invariantes, límites, procedencia y escenarios por skill del catálogo;
- fixtures de proyecto Python/backend y multiparte;
- golden manifests;
- corpus positivo/negativo de paths, hashes, symlinks, colisiones, capabilities, routing y licencias;
- `THIRD_PARTY_NOTICES.md` si se copia material MIT;
- `tests/test_generation_contracts.py` y validadores stdlib.

## Pasos

1. Derivar campos de arquitectura v3.0 y `docs/creator-preset-spec.md`.
2. Definir versión/schema y unknown-field policy.
3. Definir ownership de cada artefacto y estados Host.
4. Crear fixtures externos primero; no incluir resultados reales en repo.
5. Implementar parse/validate sin mutación parcial.
6. Crear negativos: path traversal, symlink, hash stale, manifest incompleto, routing nuevo, provider nuevo, skill huérfana, ciclo de carga, unresolved decision, extensión libre cuando aplica una base, override fuera de slots, transferencia sin aceptación destino y skill duplicada sin diferencia material.
7. Ejecutar corpus y revisar falsos positivos.
8. Actualizar `PLAN_IMPLEMENTACION.md` solo si el gate pasa.

## Gates

- todo artifact generado tiene schema y owner;
- positivo completo acepta sin DSH;
- cada negativo falla cerrado sin escritura;
- manifest exhaustivo y hashes verificables;
- fixtures no contienen rutas, credenciales ni proyectos reales.

## Adaptación autorizada

Registrar cambios de campos, compatibilidad, fixtures o límites en el run C0; una modificación contractual requiere primero arquitectura.
