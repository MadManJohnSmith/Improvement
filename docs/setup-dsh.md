# Preparación DSH: estado actual y destino 3.0

## Prerrequisito final

El usuario instala/configura DSH una vez y configura al menos un proveedor/modelo. El framework:

- no lee/copia API keys;
- reutiliza configuración efectiva de DSH;
- usa token/cookie local de consola solo en memoria para RPC;
- no modifica routing/proveedores/credenciales globales.

Si Creator/proveedor/capacidad falta, bootstrap conserva `RETAINED` con una sola acción del titular.

## Preparación comprobada actual

Standard mantiene cwd en el padre con framework/producto/workspace. `onboard.py --prepare-skills --session-root` copia skills al workspace y crea enlaces gestionados en `<padre>/.agents/skills`.

Primero dry-run, después `--init`. Repetición idempotente; entradas ajenas, enlaces alterados y overrides de mayor precedencia bloquean. `--update-skills` respalda carpetas completas antes de sustituir. `--remove-links` retira solo enlaces propios.

Los enlaces no conceden permisos ni sandbox. Un workspace por padre; padres confiables; no concurrencia hostil.

## Mecanismo comprobado del loader

El runtime comprobado descubre skills desde el cwd/proyecto y sigue enlaces de directorio. Standard monta filesystem/tool-skill. Las regresiones verifican:

- dos padres;
- cuerpos diferentes bajo mismo nombre;
- origen lógico/destino real;
- cuerpo/hash exactos;
- rechazo cruzado;
- ausencia de fuga de caché.

Ejecutar:

```bash
DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_skill_root.mjs
python3 -B -m unittest discover -s tests -v
```

## Presets y plugin actuales

Los presets de Syncify/RehabWeb y `workflow-write` demostraron composición/routing/subagentes/escritura. Son fixtures de referencia del MVP, no distribución final ni defaults de terceros. El lanzamiento automático carga `workflow-write.mjs` como overlay `--patch` (`scripts/dsh-plugins/cordis-patch.yml`) sobre el perfil del titular: sin instalación en el home DSH ni dependencias; `DSH_PLUGIN_PATCH=0` lo omite.

C4 debe empaquetar plugins/modos generados sin rutas absolutas del mantenedor y activar el conjunto mediante manifest/puntero gestionado.

## Errores de sandbox

`sandbox_permissions` es opcional y solo para escalada estrictamente mayor; el modo vigente no debe reenviarse como escalada. `workflow-write` corrige el caso observado para escritura. Error de esquema o «strictly wider» no autoriza probar `danger-full-access`.

Auditor requiere lectura producto/framework y escritura solo en workspace. Si no hay granularidad, `RETAINED`, no acceso total.

## Flujo operativo vigente

```text
<padre-común>/
├── Improvement/
├── <Proyecto>/
└── <Proyecto>-workspace/
    ├── creator-runs/
    └── mode-state/
```

`bootstrap install --launch-dsh` reutiliza una instancia DSH Web sana o inicia una
sola con `DSH_HOME` y el padre común como cwd. Crea una única sesión Creator; el
preset Creator no debe delegar, abrir subagentes ni iniciar workflows. La instancia
queda activa al terminar.

Creator genera exactamente dos presets seleccionables: `<proyecto>-auditor` y
`<proyecto>-continuous-repair`. Cada modo contiene `mode.json`, `preset.yml`,
`agent.cordis.yml` y `SKILL.md`. El Host publica ambos bajo
`$DSH_HOME/.agent-presets`, consulta `agentPresets/list` y solo considera la
instalación activa cuando ambos aparecen con `trust: user` y sin `broken`.

Los dos modos comparten exclusivamente `<Proyecto>-workspace/mode-state`; las
rutas persistidas son relativas al padre común. El producto no recibe estado del
flujo. La aceptación es determinista y veraz: valida paquete, plan, hashes y
política, pero no crea sesiones evaluator/reviewer ni afirma holdouts dinámicos.
`READY_FOR_INSTALL` autoriza la publicación; `ACTIVE` se escribe únicamente tras
publicación y roster verificados. Para pruebas e integración se debe usar siempre
un `DSH_HOME` temporal, nunca `~/.dsh`.

`scripts/bootstrap.py` implementa actualmente los subcomandos `install`, `accept`,
`finalize`, `verify-acceptance`, `update`, `uninstall` y `purge-data` descritos por
el flujo C0–C7.

## Aceptación final de una generación

Debe verificar:

- catálogo/carga/origen/cuerpo;
- capabilities y routing intactos;
- Auditor sin escritura de producto;
- Repair en candidato;
- rojo→verde;
- QA;
- reauditoría;
- checkpoint/reapertura;
- rollback/uninstall;
- post-promotion smoke.

Creator solo solicita; Host decide.
