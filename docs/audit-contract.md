# Contrato local de cobertura de auditoría

El modo completo conserva el alcance autorizado y sus dimensiones de revisión según [arquitectura §13](../ARQUITECTURA_FLUJO_AGENTES.md#13-cobertura-y-contratos). `scripts/audit.py` solo comprueba inventario, partición y estados declarados; no es un auditor semántico ni un control de permisos.

## Preparar el inventario

En una raíz estable, previamente autorizada y sin secretos, ejecutar:

```sh
python3 -B /ruta/framework/scripts/audit.py inventory \
  --product /ruta/producto --exclusions /ruta/workspace/exclusions.json \
  > /ruta/workspace/inventory.json
```

`--exclusions` es opcional. Su archivo es un objeto de rutas relativas exactas a motivos, por ejemplo `{".git": "Metadatos Git fuera de la revisión de código autorizada"}`. No hay globs, exclusiones implícitas de dependencias ni lectura de archivos de instrucciones por el script. El operador determina el alcance y autoriza las exclusiones; un motivo escrito en JSON no crea esa autoridad. Una auditoría de historia Git exige otro alcance explícito, no tratar `.git` excluido como revisado.

El inventario enumera directorios con errores visibles, ordena archivos y calcula SHA-256 por bloques. Una exclusión de archivo o directorio registra su tipo y motivo sin leer su contenido; un directorio excluido representa una frontera, no un conteo de sus archivos. Rechaza symlinks encontrados (incluido un destino de exclusión), archivos especiales, rutas absolutas o traversal y exclusiones inexistentes/anidadas. No inspecciona descendientes de una frontera excluida. No garantiza estabilidad ante escritores concurrentes hostiles; usar una copia estable o montada en lectura cuando corresponda.

## Manifiesto y consolidación

El manifiesto v1 conserva sus campos y añade `inventory`, con el objeto exacto obtenido arriba:

```json
{
  "version": 1,
  "root": "/ruta/producto",
  "inventory": {
    "version": 1,
    "files": {"src/example.py": "<sha256 real>"},
    "exclusions": {".git": {"kind": "directory", "reason": "Metadatos excluidos por el alcance autorizado"}}
  },
  "units": [
    {"unit_id": "core", "files": ["src/example.py"], "depends_on": [], "status": "ACCEPTED"}
  ]
}
```

`ACCEPTED` en una unidad es una declaración de revisión terminada, no una prueba de profundidad. Las referencias de perspectivas, decisiones y evidencia semántica permanecen en los artefactos de revisión de la unidad.

```sh
python3 -B /ruta/framework/scripts/audit.py consolidate \
  --root /ruta/workspace --manifest /ruta/workspace/manifest.json \
  --findings /ruta/workspace/findings.json --cycle-id audit-001 \
  --base-revision revision-observada
```

`findings.json` conserva la forma `{"findings": [...]}`. Cada entrada JSON de la CLI, incluido el manifiesto completo con inventario y unidades, tiene un límite de 2 MiB. El inventario emitido no reserva espacio para esa envoltura: comprobar el tamaño del manifiesto antes de consolidar; uno excesivo se rechaza sin emitir ciclo. No se soportan manifiestos ilimitados ni partición automática en fragmentos; una ampliación de ese contrato necesita trabajo y regresiones propios, no omitir archivos para encajar.

El workspace debe ser externo y no solaparse con el producto. El identificador de ciclo es un segmento de hasta 64 caracteres alfanuméricos, guiones o guiones bajos, empezando por alfanumérico. No se sobrescriben ciclos ni archivos activos existentes: conservarlos y reconciliarlos antes de otra publicación; este comando no implementa la transición automática entre ciclos.

Al consolidar:

- Reenumera la misma raíz y compara hashes/exclusiones con el snapshot. Archivos nuevos, borrados o alterados invalidan la base; falla antes de escribir el ciclo.
- Rechaza archivos duplicados por unidad, propietarios solapados, dependencias desconocidas/circulares y archivos asignados dentro de exclusiones.
- Devuelve `coverage.status: PARTITION_VERIFIED` solo si todo archivo incluido está asignado. Los omitidos quedan en `coverage_gaps`; la falta de snapshot produce `INVENTORY_MISSING`.
- Emite `UNVERIFIED` para el ciclo si la partición está incompleta/no verificada o existe alguna unidad cuyo estado no sea `ACCEPTED`. No inventa hallazgos por la mera existencia de gaps.
- Con partición verificada y todas las unidades aceptadas, conserva `AUDIT_COMPLETE` o `AUDIT_COMPLETE_WITH_RETAINED_ITEMS`, según los estados de hallazgos. Un cierre completo puede contener hallazgos retenidos; no significa producto corregido ni libre de defectos.
- Conserva la cola declarada de reparación incluso con cobertura incompleta, para permitir unidades independientes autorizadas. Su estado `READY_FOR_REPAIR` no certifica la evidencia semántica ni concede reparación.

Genera además `coverage-matrix.json` con conteos de archivos incluidos/asignados, entradas excluidas, gaps y unidades pendientes. No es una matriz que certifique lectura o doble revisión por archivo. La deduplicación existente por fingerprint tampoco valida causa ni autenticidad de hallazgos; el coordinador conserva sus evidencias originales.

## Compatibilidad y límites

La API `consolidate(root, cycle_id, base_revision, units, findings, snapshot=None)` admite consumidores anteriores. Sin snapshot no certifica cobertura: devuelve `UNVERIFIED` y conserva hallazgos/cola. Los archivos de evidencia históricos no se migran ni se recalifican automáticamente. `write_consolidated` toma el snapshot de `manifest.inventory`.

Los requisitos de doble perspectiva, prevención de recurrencia, verificación humana, memoria de decisiones y cifras de fuentes vigentes se aplican en las skills y la revisión. Este validador no los autentica ni demuestra que el agente los ejecutó. Los registros de decisiones/verificación humana y la instrumentación de métricas completas siguen siendo trabajo pendiente; cambiar un prompt no los implementa.
