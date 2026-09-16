# Plan 09 — protocolo de adaptación y aprendizaje

**Etapa:** transversal; obligatorio antes de modificar cualquier plan por evidencia nueva.
**Objetivo:** permitir que los planes se adapten sin convertirse en un backlog paralelo ni degradar los gates.

## Clasificación del cambio

| Tipo | Ejemplo | Acción |
|---|---|---|
| Hecho ambiental | versión DSH, capacidad observada | registrar fuente y ajustar precondición; no rediseñar |
| Defecto mecánico | schema inválido, race, hash incorrecto | corregir responsable + regresión mínima |
| Decisión material | nuevo root, proveedor, datos, publicación | detener y solicitar titular |
| Drift de proyecto | nueva arquitectura o comandos | nuevo discovery/contract; invalidar aceptación afectada |
| Mejora opcional | ergonomía, contexto, métrica | `P2`, nunca gate compensable |
| Cambio de contrato | estados, permisos, criterios | actualizar arquitectura antes de código |

## Ciclo de adaptación

1. Detectar la discrepancia.
2. Conservar evidencia externa y base exacta.
3. Clasificar el cambio.
4. Revisar si invalida candidatos/aceptaciones.
5. Proponer el cambio mínimo.
6. Registrar decisión y alternativas.
7. Actualizar arquitectura si el contrato cambia.
8. Actualizar plan, scripts y regresión.
9. Ejecutar positivos y negativos.
10. Actualizar estado y changelog.

## Prohibiciones

- no editar instrucciones del framework desde una misión de producto;
- no ampliar permisos para superar un fallo;
- no convertir frecuencia en calidad;
- no convertir una recomendación del modelo en autorización;
- no mover un retained a accepted por ausencia de evidencia;
- no reusar aceptación con hash/base distintos;
- no borrar un backup o un estado incierto para aparentar limpieza;
- no añadir una skill porque un hallazgo aislado lo sugiere sin procedimiento recurrente.

## Creator y drift

Una regeneración crea `creator-runs/<generation-id>` nuevo. La generación anterior sigue activa hasta que:

- el nuevo discovery identifica cambios materiales;
- los contratos se recalculan;
- scenarios/holdouts se actualizan;
- Host valida y acepta;
- backup está verificado;
- swap y post-promotion smoke pasan.

La ausencia de cambios semánticos produce `NO_OP`, no reescritura.

## Cierre adaptable

La selección de skills se reconsidera solo si cambia contrato/base o aparece una evidencia nueva. No se sustituye una base por una extensión por conveniencia.

El plan se considera vigente solo si:

- sus referencias existen;
- sus gates coinciden con arquitectura;
- sus comandos no apuntan a rutas personales;
- sus negativos siguen cubriendo los riesgos;
- el estado del índice coincide con la evidencia.

Si alguna condición falla, el plan queda `RETAINED` hasta revisión.
