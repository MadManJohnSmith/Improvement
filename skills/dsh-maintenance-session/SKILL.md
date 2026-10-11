---
name: dsh-maintenance-session
description: "Preparar una sesión DSH real como usuario final para mantenimiento o ensayo. Usar al correr un turno headless con DSH_HOME aislado, al conservar credenciales existentes sin filtrarlas, o al diagnosticar por qué una sesión no arranca; no para tareas de código sin sesión DSH."
---

# Sesión real de DSH como usuario final

## Qué demuestra este procedimiento
Una sesión real de `dsh --profile headless` dentro de un `DSH_HOME` de campaña,
con credenciales leídas dentro de un proceso. El procedimiento verificado aquí
cubre el **canal** (DSH responde de verdad). No acredita, por sí solo, que un
modo auditor/reparador/implementador complete un turno, ni el flujo
FAIL → reparación → PASS: eso se mide con otros gates.

## Preparar sin tocar la instalación previa
1. Instalar `@deepseek-ai/dsh` fijando la revisión en un directorio **externo**
   al framework canónico (`npm view @deepseek-ai/dsh version` primero; luego
   `npm install` dentro de ese directorio). No instalar bundles ni plugins de
   repositorios clonados ajenos.
2. Crear un `DSH_HOME` de campaña con **nombre propio** y ruta externa:
   `mkdir -p "$CAMP/dsh-home-<ensayo>/profiles"`.
3. Copiar el perfil `headless` (y `web` solo si procede) al `DSH_HOME` nuevo
   desde la instalación externa aislada. No copiar `node_modules/`: copia el
   perfil y deja que cada perfil resuelva sus dependencias; si un perfil web
   queda sin `node_modules`, **no arranca** y eso se dice, no se simula.
4. Copiar del home **autorizado** del operador, sin leerlos a pantalla:
   `.credentials.yaml` (modo `600`), `.anonymous-user-id`,
   `settings.yaml.imported`. Nunca borrar ni sobrescribir el `DSH_HOME`
   previo, nunca abrir el home del operador en modo escritura, nunca revocar
   credenciales.
5. Elegir el modelo desde el perfil (`agent-default-model: {provider, model}`).
   Si el perfil declara un proveedor que el home no tiene, se añade al
   `cordis.patch.yml` de **ese home de campaña**, nunca al canónico.

## Leer la credencial sin exponerla
La clave se lee **dentro de un proceso** y se pasa solo por el entorno del hijo:

```sh
DSH_HOME="$DSH_HOME_CAMPA" /usr/bin/python3 -B - <<'PY' > /tmp/nr.env
import os, yaml, pathlib, shlex
p = pathlib.Path(os.environ["DSH_HOME"]) / ".credentials.yaml"
print("export NROUTER_API_KEY=" + shlex.quote(
    yaml.safe_load(p.read_text())["refs"]["NROUTER_API_KEY"]))
PY
```

Nunca: por argumento de línea de comandos, en un archivo versionado, en un
prompt, en un log, ni en un resumen. Ningún fichero publicable puede contener
una ruta privada ni un secreto; si hace falta nombrar el recurso, se usa un
nombre de variable. Verificar que el home de campaña quedó con `600` en
`.credentials.yaml`.

## Canal real del usuario (preflight)
```sh
source /tmp/nr.env
DSH_HOME="$DSH_HOME_CAMPA" "<dsh-externo>/node_modules/.bin/dsh" \
  --profile headless --json 'Reply with exactly: PING-OK'
```
Leer eventos `session`, `step_end.usage`, `turn_end.reason.kind` y `final`:
`final.text` con `turn_end.reason.kind = completed` y `totalTokens` > 0 acredita
el canal. Un `final.text` por sí solo no es prueba de éxito funcional.

## Contabilidad real: `totalTokens`, no `input + output`
El gasto de un turno viaja en los eventos durables `assistant/message.data.usage`,
no en un resumen final. `totalTokens` **incluye las lecturas de caché**, así que
puede exceder con mucho `inputTokens + outputTokens`: medir `input + output` y
declarar el total subestima el coste. Sumar turnos sin deduplicar por `seq`
cuenta dos veces el mismo evento. El control de presupuesto se evalúa **antes**
de declarar éxito, por corrida y no por mensaje: un turno que cabría en la
quiescencia pero ya excede el límite congelado se retiene, no se acepta.

## Modo y límites de la sesión
- `--json` emite JSONL y `--session-id` reanuda una sesión persistida; la tarea
  va por argumento o por stdin (`-`).
- Si un turno headless quiesce y no escribe: el inventario puede haber caído al
  `write` del upstream porque falta el overlay. `scripts/dsh-plugins/cordis-patch.yml`
  registra `workflow-write`; sin él, el sandbox rechaza la escritura con el
  error de `sandbox_permissions`. Componer el argv con
  `creator_client.dsh_headless_command()` (o Añadir `--patch <overlay>` a mano)
  en vez de escribir el argv a pelo; `DSH_PLUGIN_PATCH=0` lanza sin overlay,
  solo para reproducir el fallo.
- El modo de sandbox de sesión (`workspace-write`) puede **negar operaciones
  fuera de su scope**, y `git worktree add` sobre un producto hermano falla con
  `Read-only file system` / `file access denied`. Un intento de escalar a
  `danger-full-access` **no se aprueba automáticamente**: sin canal de
  aprobación, queda RETAINED. El framework anti-escalada lo prohíbe por
  contrato, así que no se reintenta con otro valor.
- Si la sesión no arranca: comprueba, en este orden, el perfil sin
  `node_modules/` (no sirve), el home sin `settings.yaml`/`settings.yaml.imported`
  (adquisición lo rechaza), la clave ausente para el proveedor del modelo
  (falla por nombre de variable, nunca por valor), y el puerto 3080 ocupado.
- Un ensayo nuevo usa home, sesión y fixture nuevos: el estado heredado puede
  producir un éxito que no se ha ganado.

## Cierre de un ensayo
Registrar comando, salida y artefacto por cada afirmación funcional. Diferenciar
siempre: canal de inferencia demostrado / modo cumpliendo un turno / gate de
verificación real. Nada de esto se escribe en el árbol canónico: los logs y
artefactos van al directorio externo del ensayo.
