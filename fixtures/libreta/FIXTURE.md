# Fixture de producto: Libreta

- **Tipo:** Producto sintético mínimo: CLI de libreta de notas en Python, solo biblioteca estándar.
- **Finalidad:** Entrada de la evaluación remota: un producto completo y autocontenible sobre el que el Creator ejecuta su ciclo de auditoría. No es un golden manifest de generadores: su identidad es el digest de árbol de `product/` registrado en `project-manifest.json`.
- **Saneamiento:** Contenido sintético de autoría propia; sin rutas locales, credenciales, tokens, sesiones ni datos personales.
- **Uso:** `product/` es la raíz del producto a auditar; `FIXTURE.md` y `project-manifest.json` son el embalaje del fixture y quedan fuera del árbol auditado. Nunca se instala fuera del flujo de evaluación.
