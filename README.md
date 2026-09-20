# agent-workflow

Framework para construir y operar flujos de auditoría y reparación con DSH, evidencia verificable y comportamiento fail-closed.

## Estado

- **MVP del núcleo comprobado:** onboarding, skills, Host aislado, Auditor/Reparación, QA, reauditoría, controlador, presupuesto, archivo y recuperación acotada probados en Syncify y RehabWeb. Ver [estado](docs/status.md).
- **Arquitectura 3.0 con C0–C7 implementados:** bootstrap install/accept/update/uninstall, contrato generacional de Creator, validador Host de 10 capas, aceptación, activación transaccional y promoción, verificados sobre paquetes reales (preset cordis) y pilotos clean-room. La activación de extremo a extremo requiere una sesión DSH con proveedor configurado por el usuario. Ver [arquitectura](ARQUITECTURA_FLUJO_AGENTES.md) e [índice](PLAN_IMPLEMENTACION.md).
- **Biblioteca de skills materializada:** registro de fuentes con procedencia fijada, 21 skills base inmutables y 4 patrones de catálogo especializado activados por evidencia, con escenarios y regresión obligatoria. Ver `library/`.
- Los presets usados en Syncify/RehabWeb son **fixtures de referencia**, no defaults que deba recibir otro proyecto.

## Experiencia final (implementada en C0–C7)

Prerrequisito: DSH instalado, Creator disponible y al menos un proveedor/modelo configurado por el usuario en DSH.

```bash
python3 -B scripts/bootstrap.py install \
  --project /ruta/proyecto \
  --launch-dsh
```

Esta es la variante autónoma validada: detiene instancias DSH previas, inicia una
instancia limpia con el overlay del framework y completa Creator, aceptación Host
y activación desde el mismo comando. Omite `--launch-dsh` únicamente cuando ya
exista una instancia DSH autenticada y compatible que quieras reutilizar.

El bootstrap:

1. descubre el proyecto y prepara un workspace externo;
2. prepara el run y el prompt versionado y despacha Creator automáticamente: `--launch-dsh` detiene instancias DSH previas, inicia una instancia limpia con el plugin `workflow_write` del framework y supervisa su sesión; sin esa opción reutiliza una instancia DSH autenticada existente;
3. Creator genera `<Proyecto>-auditor`, `<Proyecto>-continuous-repair` y skills específicas justificadas, seleccionando primero la biblioteca base y el catálogo;
4. Creator invoca `bootstrap accept`;
5. el Host valida, crea backups, instala en staging y ejecuta la aceptación;
6. activa el conjunto o hace rollback/RETAINED.

El usuario no copia prompts, JSON, rutas, recibos ni escenarios de aceptación.

La activación automática de extremo a extremo corresponde a una sesión DSH real; sin ella el run queda en estado intermedio recuperable, nunca en un estado silencioso.

## Uso comprobado actual

Para mantenimiento o pilotos controlados, clona el framework junto al proyecto, nunca dentro:

```text
padre/
├── agent-workflow/
├── proyecto/
└── proyecto-workspace/
```

Preparación actual:

```bash
python3 -B scripts/onboard.py \
  --project /ruta/proyecto \
  --workspace /ruta/proyecto-workspace \
  --name mi-proyecto \
  --prepare-skills \
  --session-root /ruta/padre

# repetir con --init después de revisar el dry-run
```

Este flujo prepara perfil, skills y enlaces gestionados para mantenimiento o pilotos manuales. La generación Creator 3.0 usa `bootstrap install`; consulta [uso operativo actual](docs/usage.md) y [preparación DSH](docs/setup-dsh.md).

## Qué distribuye la arquitectura 3.0

- skills generales para bootstrap, aceptación, evidencia, validación segura y entrega;
- biblioteca base inmutable materializada (21 skills) y catálogo especializado activado por evidencia (4 patrones), con registro de fuentes y escenarios;
- capacidades internas de Creator adaptadas de scope/audit/architect/document/test/develop/check/debug/sync;
- selección obligatoria: biblioteca base inmutable → catálogo especializado → composición → override limitado → extensión Creator solo como último recurso;
- plantillas y schemas;
- validadores Host;
- bootstrap install/accept/update/uninstall/purge-data;
- backups y activación transaccional;
- plugin `workflow-write`;
- fixtures saneados, no presets universales.

## Documentación

- [Arquitectura normativa 3.0](ARQUITECTURA_FLUJO_AGENTES.md)
- [Plan C0–C7](PLAN_IMPLEMENTACION.md)
- [Contrato generacional de Creator](docs/creator-preset-spec.md)
- [Estado comprobado](docs/status.md)
- [Uso operativo actual](docs/usage.md)
- [Preparación DSH](docs/setup-dsh.md)
- [Planes detallados C0–C7](docs/plans/README.md)
- [Cambios](CHANGELOG.md)

## Seguridad y publicación

Nunca versionar perfiles reales, logs, auditorías privadas, candidatos, credenciales o rutas personales. Configurar un proveedor en DSH no autoriza al framework a leer su API key. La publicación pública y la licencia del framework siguen siendo decisiones del titular; un repositorio accesible no concede por sí solo una licencia abierta.
