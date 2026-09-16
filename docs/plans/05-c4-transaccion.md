# Plan 05 — C4: backup, instalación transaccional y desinstalación

**Salida:** activar/desactivar una generación completa sin conjunto mixto y con rollback verificable.
**Precondiciones:** C0–C3; paquete válido staged.

## Secuencia

1. Resolver ownership y colisiones.
2. Crear backup completo de cada recurso gestionado (carpeta, auxiliares, enlaces/manifest).
3. Verificar backup con hashes.
4. Construir árbol candidato hermano.
5. Validar carga/origen/cuerpo desde el candidato.
6. Ejecutar smoke mecánico.
7. Cambiar un puntero/directorio generacional gestionado.
8. Revalidar desde sesión nueva.
9. Escribir install/promotion receipt.
10. Retener backup hasta cierre de aceptación y política de retención.

## Negativos inyectados

Fallo de backup, fallo de copia, fallo de hash, proceso muerto durante staging/swap, symlink ajeno, edición local, conflicto de nombre, rollback de rename/copy, post-promotion smoke fallido, uninstall parcial y generación vieja/activa concurrente.

## Gates

- backup previo íntegro;
- candidato completo;
- activación de modos+skills como conjunto;
- rollback restaura hashes anteriores;
- uninstall retira solo ownership propio;
- no modifica producto/config global ajena;
- crash no deja mezcla ni backup destruido sin recuperación.

## Adaptación

La unidad de swap puede ser directorio, puntero o user preset root según DSH efectivo, pero debe demostrar los mismos negativos; no afirmar atomicidad portable sin prueba.
