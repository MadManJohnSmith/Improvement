# Preparación acotada de DSH

## Entrada nativa, sin overlay

Con las siete skills ya preparadas en `.agents/skills/` del workspace externo, selecciona **ese workspace como raíz de una nueva sesión Standard**, no su directorio padre. No modificar `~/.dsh`, instalar perfiles ni alterar presets.

Prompt de aceptación:

> Comprueba el catálogo y carga `project-onboarding` mediante la herramienta nativa `skill`. Informa proveedor, origen y una instrucción del cuerpo. Solo aceptación de carga: no ejecutes onboarding ni operaciones de producto; no edites archivos ni configuración. Si falta, informa el error real sin improvisar instalaciones.

## Mecanismo comprobado

Inspeccionado y ejecutado el runtime instalado DSH **0.1.5-rc.1**, Node **26.8.1**. El proveedor filesystem busca un ancestro `.git`; si no existe, usa exactamente el `cwd` solicitado. No busca workspaces hijos. El inicializador exige un workspace fuera de repositorios Git: su raíz de sesión resuelve `.agents/skills` sin configuración adicional.

La herramienta usa `agent.session.header.cwd` y el alcance del agente. El override retirado configuraba la fila global `skill-filesystem`, desactivada por Web, no la fila propia del preset Standard. No era una solución efectiva. Se mantienen las raíces por defecto del preset; no se añaden proveedores globales ni se suprimen defaults.

## Regresión sin modelos

```sh
DSH_MODULE_ROOT=/absolute/installed/node_modules node tests/test_dsh_skill_root.mjs
python3 -B -m unittest discover -s tests -v
```

El test Node importa Cordis, registro, proveedor filesystem y herramienta instalados; monta proveedor/herramienta en un alcance, compara padre (0) y workspace (7), ejecuta `ctx.tools.execute` para las siete skills y verifica cuerpo completo, origen y SHA-256. Crea únicamente fixtures temporales externos y redirige raíces personales a destinos temporales vacíos. Admite un workspace existente como argumento adicional, solo lectura. No inicia servidor, proveedor de modelos ni sesión LLM. No reproduce todo el Host ni certifica el montaje GUI Standard.

La carga determinista nativa está comprobada; la aceptación con el modelo en la sesión del usuario sigue pendiente. Producto fuera del workspace no queda autorizado por seleccionar esta raíz: lectura/escritura posterior depende de permisos efectivos del Host y mandato separado. `framework_clean()` es una consulta Git no invocada por el inicializador, no una barrera de seguridad ni aislamiento OS.
