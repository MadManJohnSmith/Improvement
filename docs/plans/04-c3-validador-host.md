# Plan 04 — C3: validador Host de generación

**Salida:** validador independiente de paquetes Creator, fail-closed y sin escrituras activas.
**Precondiciones:** C0 schemas/corpus; C2 genera al menos un fixture.

## Capas

1. schema/version/unknown fields;
2. manifest exhaustivo, hashes, file types, paths y symlinks;
3. graph de referencias, ciclos y hot paths;
4. contracts/requirements/source provenance;
5. capabilities, roots, tools, models y routing;
6. portability, scripts, subprocess, red y datos;
7. context budgets;
8. collision/ownership/precedence;
9. licencia/THIRD_PARTY_NOTICES;
10. anti-autoapproval y lifecycle.

## Pasos

- reutilizar validadores actuales solo donde el contrato coincida;
- crear CLI/API pura sin mutación;
- producir reportes separados por capa;
- crear corpus negativo por cada regla;
- enlazar cada rejection a una ruta/campo/claim;
- distinguir `RETAINED`, `REJECTED`, `BLOCKED`, `UNVERIFIED`.

## Gate

Todo negativo falla cerrado antes de backup/install; positivo completo produce `READY_FOR_ACCEPTANCE`; reportes son reproducibles desde bytes/manifests.

## Adaptación

Los thresholds de bytes/hot path y allowlists se fijan después de medir C2, nunca se elevan para hacer pasar un candidato.
