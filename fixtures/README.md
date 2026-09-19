# Fixtures de referencia saneados

Este directorio contiene fixtures de prueba derivados de proyectos reales (Syncify y RehabWeb)
saneados conforme a la sección 4.6 de `ARQUITECTURA_FLUJO_AGENTES.md`.

## Reglas de los fixtures

1. **Explicitamente marcados como fixtures:** no son código de producción ni defaults distribuibles.
2. **Sin rutas locales ni identidades:** no contienen rutas de usuario, claves, tokens ni sesiones.
3. **Golden manifests:** sirven exclusivamente para validar generadores y validadores de contratos (C0–C3).
4. **Nunca se instalan automáticamente:** Creator debe generar paquetes específicos por proyecto.
