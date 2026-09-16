1. Modificar únicamente los dos lanzadores externos de `/home/alan/DSH-workspace/launchers/`:
   - definir `PROFILE=${DSH_PROFILE:-web}`;
   - arrancar con `node "$BIN" --profile "$PROFILE" --host ... --port ...`, sin combinar el alias `web` con `--profile`;
   - conservar el runtime compartido, porque el inventario confirma que RehabWeb no tiene una instalación propia y duplicarla no aporta aislamiento: el aislamiento real está en `DSH_HOME`, caché y puerto.
2. Añadir una comprobación permanente y pequeña en el repositorio canónico, sin usar datos reales: un test que lea ambos launchers y verifique que cada uno conserva su home/caché/puerto, usa el runtime común esperado y selecciona el perfil explícitamente con fallback `web`. No ejecutará DSH ni escribirá en `/home/alan/DSH-workspace`.
3. Actualizar `docs/setup-dsh.md` con la decisión operativa: runtime compartido intencional, aislamiento por home/caché/puerto y perfil CLI explícito; documentar `DSH_PROFILE` para perfiles alternativos.
4. Ejecutar la nueva regresión y la suite Python existente con `python3 -B`, usando salidas externas; revisar el diff sin tocar ni limpiar los cambios preexistentes del árbol canónico.