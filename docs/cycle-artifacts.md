# Artefactos de ciclos

Los ciclos viven fuera del framework y del producto. La carpeta activa es un índice compacto; el detalle cerrado se conserva en un archivo por ciclo.

El árbol siguiente describe la organización objetivo, no todos los archivos emitidos por un único script. Para usar el consolidador local, seguir [docs/audit-contract.md](audit-contract.md): el directorio de ejecución conserva `started.json`/checkpoint/cierre y el helper crea un destino de ciclo nuevo con manifiesto, matriz de partición y cola. La sustitución de `active/` entre ciclos no está automatizada y no se sobrescribe. Decisiones y verificación humana son registros externos de revisión, no servicios validados por ese helper.

```text
<external-root>/
├── active/
│   ├── current-cycle.json
│   ├── current-summary.md
│   ├── audit-manifest.json
│   ├── repair-queue.json
│   ├── decisions.json
│   └── exceptions.json
├── cycles/<cycle-id>/
│   ├── started.json
│   ├── manifest.json
│   ├── checkpoint.json
│   ├── summary.md
│   ├── units/<unit-id>/
│   └── repairs/<finding-id>/
├── archive/<cycle-id>/
│   ├── index.json
│   ├── summary.md
│   └── evidence/
└── cache/inventory/<base-hash>.json
```

## Reglas

- Crear un `cycle-id` nuevo y `started.json` antes de trabajar.
- No mezclar ciclos, sobrescribir cierres ni reutilizar un archivo previo como estado activo.
- `active/` conserva solo el ciclo vigente, decisiones actuales, excepciones abiertas y referencias compactas.
- Informes extensos, logs, diffs, candidatos terminados y decisiones sustituidas pasan a `archive/<cycle-id>/`.
- La cola activa conserva hallazgos pendientes y `resolved_ref`; el detalle resuelto queda archivado.
- Cada `index.json` registra ciclo, base, estado, unidades, hallazgos, hashes y advertencias de rutas históricas.
- El historial no se carga automáticamente en prompts. Recuperar primero estado, resumen, cola y decisiones; leer evidencia puntual solo cuando el criterio lo requiera.
- Una caché se reutiliza solo con la misma base y reglas compatibles. Nunca contiene autoridad.
- Mover o archivar no convierte un resultado antiguo en evidencia vigente: comprobar hashes y base antes de reutilizarlo.

## Estados

`READY_FOR_REPAIR` es la única entrada activa de reparación. `RETAINED`, `UNVERIFIED`, `NEEDS_DECISION`, `STALE` y `DUPLICATE` permanecen fuera de la cola ejecutable hasta una decisión o evidencia nueva.
