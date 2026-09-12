# Especificación neutral para Creator/Cordis

Esta especificación se entrega a Creator para componer un preset externo. No es un preset activo ni concede permisos.

## Entrada requerida

- Framework externo con `skills/workflow-complete-auditor/SKILL.md`.
- DSH/Cordis y esquema efectivos identificados por el Host.
- Workspace externo escribible.
- Routing, proveedores, modelos, aliases y credenciales ya existentes que deben conservarse.

## Salida única

Creator debe escribir únicamente en el workspace externo:

```text
preset.yml
agent.cordis.yml
```

No escribir en `~/.dsh`, `~/.agents`, repositorios, credenciales, configuración global ni producto.

## Composición mínima

El preset debe:

1. cargar la skill `workflow-complete-auditor` mediante la herramienta nativa `skill`;
2. exponer filesystem/search para lectura del producto;
3. exponer escritura solo en el workspace/ciclo externo autorizado;
4. exponer subagent/workflow solo si ya existen en el runtime;
5. conservar el routing efectivo y no declarar proveedores o modelos nuevos;
6. permitir validadores stdlib enumerados por la misión;
7. bloquear escritura del producto durante Auditoría;
8. registrar capacidades no observables como `UNVERIFIED`.

No añadir red, instalación, publicación, integración, goals ilimitados ni plugins no justificados.

## Prueba mínima de aceptación

La prueba debe limitarse a:

- cargar el preset;
- comprobar la skill, origen y cuerpo;
- enumerar herramientas efectivas;
- confirmar que no cambió routing;
- confirmar que el destino de escritura es externo.

No ejecutar una auditoría, reparación, build o prueba de producto durante la aceptación del preset.

## Prompt para Creator

> Crea un preset Cordis neutral de Auditoría completa para este framework. Carga `workflow-complete-auditor`, permite lectura del producto, escritura únicamente en el workspace externo y delegación a subagentes solo si el runtime ya la ofrece. Conserva la versión y routing efectivos; no modifiques `~/.dsh`, credenciales, proveedores, modelos, aliases, presets distribuidos, producto ni framework. No añadas red, instalación, publicación o integración. Escribe únicamente `preset.yml` y `agent.cordis.yml` en el workspace externo e incluye una prueba mínima de carga sin ejecutar auditorías ni cambios.
