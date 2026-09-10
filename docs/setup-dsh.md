# Preparación acotada de DSH

No hay instalación ni activación automática. El inicializador Python funciona sin DSH. No modificar `~/.dsh`, modelos, proveedores o presets distribuidos para seguir esta guía.

## Compatibilidad conocida

El usuario reportó DSH **0.1.5-rc.1** y un loader con raíces `.dsh/skills` y `.agents/skills` condicionadas por configuración. El paquete instalado reportado no estuvo disponible para lectura en esta reorganización; no se presenta como comprobación actual de esa versión.

Se inspeccionó la fuente local suministrada `packages/skill/skill-filesystem/src/index.ts`: `Config` admite `includeDefaultRoots`, `customSkillDirs`, `dshHome`, `agentsHome`; el proveedor descubre `SKILL.md`, separa catálogo y carga de cuerpo, y resuelve raíces respecto al proyecto efectivo. Esa fuente no acredita equivalencia con el binario rc.1. No copiar ejemplos `persona.text`/`prefix` sin comprobar el esquema efectivo.

## Configuración de skills por proyecto

Copiar skills al workspace externo no activa el proveedor en una sesión ya iniciada. En el runtime 0.1.5-rc.1 reportado, `@deepseek-ai/dsh-skill-filesystem` admite `customSkillDirs`, `includeDefaultRoots`, `dshHome` y `agentsHome`. El perfil Web puede desactivar la fila global y dejar que el preset la monte; por eso la configuración efectiva del preset debe inspeccionarse antes de probar.

Usa una sola estrategia en un Host/perfil dedicado:

```yaml
# Fragmento conceptual: adaptar al patch/config real comprobado; no pegar sin validar el esquema.
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  config:
    includeDefaultRoots: false
    customSkillDirs:
      - /ruta/absoluta/al/workspace/.agents/skills
```

Este fragmento no es un preset completo ni una orden para modificar `~/.dsh`. La ruta debe ser externa al producto y específica del workspace. Si el preset efectivo monta `skill-filesystem` dentro del alcance del agente, el override debe aplicarse a esa fila/preset y no a una raíz global. No mezclar `customSkillDirs` con copias globales para aparentar descubrimiento. Después de reiniciar la sesión, comprobar por separado catálogo, origen, carga del cuerpo y ejecución de una skill. Si la API real no acepta el fragmento, conservar el error y adaptar el overlay a su DSL; no cambiar `text`/`prefix` ni otros presets por analogía.

## Procedimiento sin sobrescritura

1. Identificar ejecutable, paquete/version real, Host, preset efectivo y entorno dedicado autorizado. No instalar ni iniciar llamadas LLM sin presupuesto.
2. Verificar que el proveedor filesystem y la herramienta `skill` estén montados. Consultar su configuración efectiva, no inventar un archivo raíz Cordis.
3. Preferir configurar **solo ese proveedor en el Host dedicado** con `includeDefaultRoots: false` y `customSkillDirs` conteniendo la ruta absoluta al `skills/` de este clon. Es un fragmento de opciones del proveedor, no un preset completo ni una orden de instalación. Comprobar estas opciones en la versión real antes de aplicarlas.
4. Alternativa: copiar explícitamente los cinco directorios de `skills/` a `.dsh/skills` del workspace externo, solo si la raíz de proyecto efectiva es ese workspace y las raíces por defecto están habilitadas. Si existe cualquier destino, comparar y detenerse ante diferencias: no usar copia con sobrescritura. No instalar en el producto ni en directorios personales. Evitar activar ambas alternativas y familias duplicadas.
5. Enumerar el catálogo y comprobar nombre, descripción y origen de cada skill; cargar `project-onboarding` con la herramienta real y comprobar su cuerpo. Metadata anunciada no demuestra carga.
6. Con autorización, probar proyecto desechable: dry-run, creación explícita y repetición sin cambios. Registrar comando, versión, resultado, límites y consumo. Una sesión LLM real requiere autorización separada; un driver no la sustituye.

## Criterio de salida

No declarar onboarding DSH operativo hasta observar descubrimiento, carga y ejecución real. Casos pendientes para evaluación: incorporar proyecto nuevo; reutilizar perfil con decisiones humanas; rechazar enlace o destino conflictivo. Las pruebas Python cubren el inicializador, no el comportamiento de los modelos. Auditor y Reparación continua aún requieren presets, permisos efectivos y coordinación comprobados.
