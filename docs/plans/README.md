# Planes de implementación de arquitectura 3.0

Estos documentos descomponen la arquitectura aprobada en iteraciones adaptables. No sustituyen `ARQUITECTURA_FLUJO_AGENTES.md` ni `PLAN_IMPLEMENTACION.md`:

- `ARQUITECTURA_FLUJO_AGENTES.md` es la norma.
- `PLAN_IMPLEMENTACION.md` es el índice único de progreso.
- `docs/plans/` contiene procedimientos detallados para ejecutar cada etapa y actualizarla sin crear backlogs paralelos.
- `docs/status.md` conserva los hechos comprobados.

## Orden

1. [00 — mapa general y gobierno de implementación](00-mapa-y-gobierno.md)
2. [01 — C0: contratos, schemas y fixtures](01-c0-contratos-fixtures.md)
3. [02 — C1: bootstrap determinista](02-c1-bootstrap.md)
4. [03 — C2: automatización Creator](03-c2-creator.md)
5. [04 — C3: validador Host](04-c3-validador-host.md)
6. [05 — C4: backups e instalación transaccional](05-c4-transaccion.md)
7. [06 — C5: aceptación automática](06-c5-aceptacion.md)
8. [07 — C6: piloto clean-room](07-c6-piloto.md)
9. [08 — C7: promoción y distribución](08-c7-promocion.md)
10. [09 — protocolo de adaptación y aprendizaje](09-adaptacion.md)

## Cómo usar los planes

Cada plan es una propuesta ejecutable, no una licencia para saltar autoridad. Antes de comenzar una etapa:

1. leer arquitectura, índice y plan de la etapa;
2. comprobar que las precondiciones siguen vigentes;
3. copiar el plan a un `run` externo con `run_id`, base, presupuesto y responsable;
4. ajustar solo la sección **Adaptación autorizada** y registrar el motivo;
5. ejecutar pasos en orden, preservando trabajo ajeno;
6. verificar negativos antes de marcar gates;
7. actualizar únicamente la fila de `PLAN_IMPLEMENTACION.md` y `docs/status.md`;
8. registrar decisiones y cambios en `CHANGELOG.md`;
9. commit local solo tras revisión del diff; publicación separada y explícita.

Un plan puede terminar `HECHO`, `PARCIAL`, `RETENIDO` o `BLOQUEADO`; nunca se declara completo por haber ejecutado comandos.
