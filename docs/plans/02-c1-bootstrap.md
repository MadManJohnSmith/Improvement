# Plan 02 — C1: bootstrap determinista

**Salida:** `scripts/bootstrap.py install` prepara un `creator-run` sin tocar producto/configuración global.
**Precondiciones:** C0 aprobado; DSH y Creator instalados; proveedor/modelo ya configurado por el usuario.

## Pasos

1. Validar proyecto/framework/workspace, roots y solapamientos.
2. Comprobar DSH, Creator, canal local y capability mínima sin abrir credenciales.
3. Crear generation-id, `started.json`, presupuesto y snapshot.
4. Inventariar Git, manifests, instrucciones, áreas y exclusiones sin ejecutar producto.
5. Preparar skills generales con ownership, idempotencia y conflictos.
6. Crear `inputs/` y `discovery/` iniciales.
7. Preparar el paquete de llamada Creator y el prompt versionado.
8. Hacer checkpoint y retornar una referencia compacta.
9. Implementar `update`, `uninstall` y `purge-data` solo después de install mínimo, con ownership estricto.

## Negativos

- proveedor ausente;
- Creator ausente;
- workspace dentro del producto/framework;
- root symlink/solapada;
- configuración global no disponible;
- skill ajena/conflicto;
- generación existente;
- secreto detectado en inputs;
- interrupción antes de completar snapshot.

## Gates

Clone limpio + proveedor configurado → un comando crea run completo; repetición es no-op; producto y configuración global sin cambios; errores dejan checkpoint RETAINED.

## Adaptación autorizada

La convención de workspace, cliente local DSH, nombres de skills generales y política de datos pueden ajustarse tras un ensayo clean-room, conservando el contrato y registrando el motivo.
