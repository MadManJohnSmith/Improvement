# agent-workflow

Método reusable de auditoría y reparación con agentes. Clona este repositorio **junto a cualquier proyecto**, no dentro. Versión operativa v0.1: incorporación, Auditor y Reparación continua acotada en Standard; no es todavía un motor autónomo DSH.

## Inicio con DSH Standard

Con este clon junto al proyecto, pide al agente: **«Lee START.md de este framework e incorpora el proyecto vecino que te indico, sin modificar su producto.»** Identifica el archivo por su ruta relativa si la sesión está abierta en el producto. [START.md](START.md) contiene el procedimiento, límites y devolución: el usuario no necesita copiarlos en cada turno.

El clon de consumo se actualiza mediante pull; no se utiliza para editar el framework ni guardar resultados de ensayos. Las correcciones del flujo se realizan en el repositorio del mantenedor, se verifican, se comitean y se publican al remoto autorizado antes del siguiente ensayo. Cada devolución identifica la revisión probada. No es una sincronización automática de sesiones.

Con skills preparadas y enlaces gestionados mediante `--session-root`, conserva la misma raíz padre de Standard. No requiere overlay, perfil dedicado ni cambiar cwd. [Aceptación nativa y prueba sin modelos](docs/setup-dsh.md).

## Inicio por CLI

Requisito: Python 3.9+; Git solo para versionar el framework. Desde el clon:

```sh
python3 -B scripts/onboard.py --project /ruta/proyecto --workspace /ruta/proyecto-workspace --name mi-proyecto
python3 -B scripts/onboard.py --project /ruta/proyecto --workspace /ruta/proyecto-workspace --name mi-proyecto --init
python3 -B -m unittest discover -s tests -v
```

Sustituye las rutas por destinos absolutos reales. Proyecto y padre del workspace deben existir. La primera orden no escribe; `--init` crea únicamente `PROJECT.md` y `project.json`, con directorio privado. Una repetición compatible conserva las decisiones; conflictos o inicializaciones incompletas se rechazan sin borrar. No usar padres mutables por terceros: validación de rutas no es sandbox ni protección contra carreras hostiles.

```text
carpeta/
├── agent-workflow/         # framework versionable
├── proyecto/               # producto, nunca inicializado por este script
└── proyecto-workspace/     # perfil y evidencia privados
```

Revisa instrucciones y canónicos del proyecto, completa el primer encargo y sus límites en el perfil. No se crean dashboards, no se ejecuta código del producto ni se instalan dependencias o skills automáticamente. El workspace privado no sustituye un entorno aislado de pruebas; revisa permisos, backups y sincronización.

## Uso con agentes

Los dos modos finales son **Auditor** y **Reparación continua**, con incorporación compartida y Ejecutor/QA internos. Disponibles como skills conductuales de una unidad en Standard, no presets ni autonomía Host. Protocolo ejecutable y prompt breve en [docs/usage.md](docs/usage.md).

- [Arquitectura completa](ARQUITECTURA_FLUJO_AGENTES.md).
- [Preparación DSH y límites del loader](docs/setup-dsh.md).
- [Estado y evidencia](docs/status.md).
- [Cambios de distribución](CHANGELOG.md).
- `skills/`: incorporación, evidencia, validación segura, aceptación acotada y entrega proporcional.

Search y otros asesores son opcionales para mantenedores; no son una dependencia del usuario. No hay CI, instalador global, modelos configurados ni llamadas a proveedores.

## Publicación

Versionar solo el framework revisado. Nunca agregar perfiles reales, logs, auditorías privadas, candidatos, archivos históricos ni credenciales. `.gitignore` es una ayuda, no una revisión de seguridad. No se incluye remoto. **Licencia pendiente de decisión del titular**: esta distribución no concede una licencia abierta por estar preparada para GitHub.
