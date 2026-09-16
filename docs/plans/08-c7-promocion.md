# Plan 08 — C7: promoción y distribución

**Salida:** versión piloto reproducible, documentada y legalmente distribuible.
**Precondiciones:** C0–C6.

## Pasos

1. Reconciliar resultados, retenciones, drift, rollback y feedback.
2. Actualizar arquitectura/índice/status/guías solo con hechos.
3. Ejecutar suites y validadores desde un clone nuevo.
4. Resolver licencia del framework.
5. Añadir `THIRD_PARTY_NOTICES.md` si se reutilizó código/texto MIT u otra licencia.
6. Revisar procedencia, datos privados, rutas y secretos.
7. Crear tag de piloto.
8. Publicar solo en destino/alcance autorizados.
9. Repetir clean-room desde el tag.
10. Emitir informe de límites y feedback.

## Gate

- tag reproducible;
- clone limpio + proveedor DSH preparado;
- bootstrap/Creator/accept/rollback demostrados;
- documentos y licencia coherentes;
- no rutas/identidades del mantenedor;
- feedback y límites visibles;
- publicación autorizada o retención explícita.

La ausencia de publicación pública no bloquea el MVP técnico si la distribución privada autorizada está acreditada.

## Adaptación

El destino, licencia, avisos y alcance de publicación son decisiones del titular. La falta de autorización conserva C7 `BLOQUEADO`, no se convierte en éxito por tener commits locales.
