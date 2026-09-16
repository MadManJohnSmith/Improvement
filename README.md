# agent-workflow

Framework para construir y operar flujos de auditoría y reparación con DSH, evidencia verificable y comportamiento fail-closed.

## Estado

- **MVP del núcleo comprobado:** onboarding, skills, Host aislado, Auditor/Reparación, QA, reauditoría, controlador, presupuesto, archivo y recuperación acotada probados en Syncify y RehabWeb. Ver [estado](docs/status.md).
- **Arquitectura 3.0 aprobada, pendiente de C0–C7:** el flujo final será de un comando y generará modos/skills específicos de cada proyecto mediante DSH Creator. Ver [arquitectura](ARQUITECTURA_FLUJO_AGENTES.md) e [índice](PLAN_IMPLEMENTACION.md).
- Los presets usados en Syncify/RehabWeb son **fixtures de referencia**, no defaults que deba recibir otro proyecto.

## Experiencia final objetivo (aún no implementada)

Prerrequisito: DSH instalado, Creator disponible y al menos un proveedor/modelo configurado por el usuario en DSH.

```bash
python3 -B scripts/bootstrap.py install --project /ruta/proyecto
```

El bootstrap deberá:

1. descubrir el proyecto y preparar un workspace externo;
2. llamar automáticamente a DSH Creator mediante la API local autenticada;
3. generar `<Proyecto>-auditor`, `<Proyecto>-continuous-repair` y skills específicas justificadas;
4. hacer que Creator invoque `bootstrap accept`;
5. validar mediante Host, crear backups, instalar en staging y ejecutar aceptación automática;
6. activar el conjunto o hacer rollback/RETAINED.

El usuario no copiará prompts, JSON, rutas, recibos ni escenarios de aceptación.

Esta interfaz pertenece a C0–C7 y **todavía no está disponible**.

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

Este flujo prepara perfil, skills y enlaces gestionados. No implementa todavía la generación Creator 3.0 ni instala modos finales específicos automáticamente. Consulta [uso operativo actual](docs/usage.md) y [preparación DSH](docs/setup-dsh.md).

## Qué distribuye la arquitectura 3.0

- skills generales;
- capacidades internas de Creator adaptadas de scope/audit/architect/document/test/develop/check/debug/sync;
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
- [Cambios](CHANGELOG.md)

## Seguridad y publicación

Nunca versionar perfiles reales, logs, auditorías privadas, candidatos, credenciales o rutas personales. Configurar un proveedor en DSH no autoriza al framework a leer su API key. La publicación pública y la licencia del framework siguen siendo decisiones del titular; un repositorio accesible no concede por sí solo una licencia abierta.
