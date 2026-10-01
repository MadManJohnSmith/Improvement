# Preparación DSH: estado actual y destino 3.0

## Prerrequisito final

El usuario instala/configura DSH una vez y configura al menos un proveedor/modelo. El framework:

- no lee/copia API keys;
- reutiliza configuración efectiva de DSH;
- usa token/cookie local de consola solo en memoria para RPC;
- no modifica routing/proveedores/credenciales globales.

Si Creator/proveedor/capacidad falta, bootstrap conserva `RETAINED` con una sola acción del titular.

## Pruebas contra el runtime instalado
Dos regresiones levantan el runtime DSH de verdad y **se saltan si no encuentran `DSH_MODULE_ROOT`**, así que una suite en verde no dice nada sobre ellas mientras la variable no esté puesta:

```bash
DSH_MODULE_ROOT=/ruta/absoluta/al/node_modules python3 -B -m unittest discover -s tests
```

`test_real_services_and_fail_closed` levanta `ctx.fs`, `ctx.shell`, `ctx.subprocess` y `ctx.sandboxPolicy` y comprueba la denegación real: el producto queda intacto ante un intento de escritura y un proceso descendiente también queda bloqueado. `test_same_mode_escalation_writes_and_outside_denied` monta un preset por agente y necesita **`@deepseek-ai/dsh-agent-preset`, que no se publica hasta 0.1.7-alpha.1**; con un runtime anterior se salta nombrando la versión que falta.

Un `skip` por defecto no es una prueba: si una de estas deja de correr porque el entorno cambió, el fallo se camufla de salto verde. Si tocas una prueba viva, ejecútala con la variable puesta antes de darla por buena.
`tests/test_auditor_confinement.py` es la tercera, y es la que mide D2. Levanta el runtime con la política apuntando al **workspace** y comprueba, en la misma corrida, lo que decide el diseño: la bash lee el producto pero no puede escribirlo (`EROFS` real, y los descendientes heredan la frontera), `ctx.fs` tampoco lo alcanza, y el auditor **sigue pudiendo escribir su `mode-state`**. La regresión incluye el negativo: con la política en la raíz de sesión, que es lo que hace la composición actual, el producto sí se clobbera.
Dos detalles que solo se ven ejecutando. La sesión **no debe vivir bajo `/tmp`**: `/tmp` es raíz escribible del sandbox y se remonta, así que un producto alojado ahí desaparece en vez de quedar en solo lectura —se lee como «archivo inexistente», no como denegación—. Y `writableRoots()` del runtime admite **una sola** raíz configurable: por eso el auditor se confina pero el reparador no, que necesita su candidata y su estado a la vez.

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
`agent.cordis.yml` y `SKILL.md`. Su composición debe montar persona, bash, fs,
fs-search, skill-filesystem y tool-skill; el Host retiene una composición incompleta
o con filas de subagente/delegación, workflow, web/red o plugin-manager. Cada
`SKILL.md` de modo o skill lleva `name` idéntico al directorio y `description` no
vacía.

El Host materializa un bundle de declaraciones `@deepseek-ai/dsh-agent-preset`,
copia todas las skills y recursos generados y cada skill de modo bajo
`bundle/skills/<name>`, y reconfigura cada `dsh-skill-filesystem` con
`includeDefaultRoots: false` y `customSkillDirs` apuntando al root absoluto del
bundle. Colisiones, symlinks y entradas no regulares bloquean la instalación. Luego
instala mediante `pluginManager/installBundle`, consulta `agentPresets/list` y solo
considera la instalación activa cuando ambos IDs del recibo aparecen sin diagnóstico
`broken`. El runtime vigente ya no lee la ruta legacy `$DSH_HOME/.agent-presets`.

Los dos modos comparten `<Proyecto>-workspace/mode-state`; Host preflightea e
inicializa schemas estrictos, caps de archivo/registro y slot candidato. La persona
obliga a cargar primero el skill homónimo. Auditor solo usa `workflow_write` para
estado. Repair no usa write/edit; cambia código por bash con workdir candidato,
deriva identidad con full base+IDs, verifica invariantes canónicas pre/post y no
commitea por un prompt simple. Los reemplazos son por archivo, no transacción
multiarchivo; no existe CAS/lease ni confinamiento mecánico de bash, por lo que el
lifecycle sigue EN CURSO hasta piloto DSH real. Las rutas son relativas al padre. El
producto no recibe estado del flujo. La aceptación es determinista y veraz: valida paquete, plan, hashes y
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
