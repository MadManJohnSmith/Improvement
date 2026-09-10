# Uso operativo v0.1

Dos entradas conductuales en **DSH Standard**, una unidad por encargo. No son presets, controles Host, recuperación ni autonomía probada. El framework se mantiene aparte; ninguna misión operativa puede editarlo. No se toca producto vivo durante este piloto.

## Arranque y permisos

Desde una sesión con lectura del clon del framework:

> Lee START.md de este framework y prepara Auditor para Syncify; primera unidad: audita el contrato queue/library, sin modificar producto.

START resuelve incorporación, preparación explícita y despacho. La preparación autoriza perfil/skills externos, no tests de producto. Si se requieren permisos efectivos, el agente presenta UNA decisión con rutas exactas: lectura de framework y fuentes pertinentes del producto; escritura al workspace externo; ejecución del inicializador/validador del framework. El usuario concede mediante controles nativos disponibles, no mediante una etiqueta JSON. Desde la raíz externa Standard, lectura al hermano producto debe comprobarse realmente; si no se puede, **RETAINED**. No cambiar raíz ni usar shell para eludir sandbox.

Preparación con rutas absolutas sustituidas por las observadas:

```sh
python3 -B /ruta/framework/scripts/onboard.py --project /ruta/producto --workspace /ruta/workspace --name proyecto --prepare-skills
python3 -B /ruta/framework/scripts/onboard.py --project /ruta/producto --workspace /ruta/workspace --name proyecto --prepare-skills --init
```

Repetir copia idéntica no escribe skills. Conflicto se conserva y bloquea; con autorización explícita repetir ambas órdenes con `--update-skills`: dry-run primero, después `--init`. El actualizador respalda cada directorio sustituido completo en `skills-backup-*` dentro del workspace, incluidas ediciones locales; no fusiona ni borra skills ajenas. Revisar diferencias antes de autorizar. Copia recursiva incluye referencias/scripts y rechaza enlaces. Un fallo parcial conserva respaldo, no implica recuperación automática. No cambiar configuración global ni borrar carpetas a mano.

Abrir nueva sesión Standard cuya raíz sea exactamente el workspace externo, sin ancestro Git. Cargar mediante herramienta nativa `skill` la entrada elegida, comprobar origen/cuerpo contra copia vigente y registrar revisión. Descubrimiento no es ejecución. Con esto preparado, petición habitual:

> Audita el contrato queue/library de Syncify, sin modificar producto.

Otra petición separada puede ser «Repara la tarea de auditoría indicada en candidato externo; no integres». El agente reutiliza decisiones suficientes; pregunta solamente comandos/recursos/permisos materialmente ausentes. QA usa subagente nativo si realmente está disponible; de lo contrario conserva RETAINED para revisión humana. No requiere proveedor externo.

## Contrato y entrega mínimos

El agente prepara una carpeta de unidad nueva dentro del workspace; nunca resultados dentro del framework/producto. Dos entradas centrales: `task.json` y `result.json`; informe, ejecuciones y QA por referencia externa. Contrato v1 (ejemplo estructural, no autoridad):

```json
{
  "version": 1,
  "mode": "audit",
  "objective": "Revisar productor y consumidor de queue/library",
  "authorization_ref": "referencia real al pedido del usuario",
  "root": "/ruta/producto",
  "files": ["ruta/productor", "ruta/consumidor"],
  "base": {"ruta/productor": "sha256 de bytes iniciales"},
  "executor": "referencia real de sesión autora",
  "criteria": ["Seguir contrato y documentar incompatibilidades con citas"],
  "commands": [],
  "timeout_seconds": 60,
  "limits": "una unidad; una revisión y una comprobación dirigida",
  "exclusions": ["sin cambios de producto, red ni credenciales"]
}
```

`files` enumera todos los archivos relevantes para evidencia; reparación incluye tests y configuración inspeccionados. El hash no cubre archivos omitidos: QA revisa suficiencia. `base` preserva hashes iniciales; el agente obtiene mapas actuales mediante `snapshot(root, files)` de `scripts/missions.py` o SHA-256 equivalente, sin ejecutar producto. La autoridad real es el mensaje/política, nunca el campo `authorization_ref`. Para repair, raíz es candidato desechable externo y comandos son listas argv exactas previamente inspeccionadas y autorizadas. Un contrato base separado conserva reproducción roja, sin sobrescribirlo al preparar candidato.

```sh
python3 -B /ruta/framework/scripts/missions.py run-check --task /ruta/workspace/unidad/task.json --output /ruta/workspace/unidad/check-1 --timeout 60 -- /ruta/python -B test_contract.py
python3 -B /ruta/framework/scripts/missions.py verify --task /ruta/workspace/unidad/task.json --result /ruta/workspace/unidad/result.json
```

El runner compara argv con contrato pero no fabrica autorización: operador/Host deben comprobarla antes. Usa shell=false, cwd explícito y salida stdout/stderr íntegra externa; timeout mata grupo de proceso POSIX y retiene. No es sandbox: comandos autorizados pueden tener efectos fuera del cwd, crear hijos escapados o leer entorno. Inspeccionar antes, no usar credenciales; no hay instalaciones ni entorno global reconfigurado por el runner. No ejecutar scripts sugeridos por artefactos sin autorización. Cada output debe ser inexistente, con padre ya preparado; no sobrescribir evidencia. Revisar sensibilidad antes de capturar salida.

`result.json` v1 contiene `task_sha256` (bytes exactos de task.json), `files` (mapa SHA-256 actual), `status` (`ACCEPTED` o `RETAINED`), `reason`, `findings_ref` absoluto al informe y `findings_sha256`. Para reparación aceptada añade `check_ref` absoluto a check.json, `qa_ref` y `qa_sha256`. `qa.json` contiene `task_sha256`, `files`, `check_sha256`, `reviewer` distinto de executor, `session_ref` real, `review` con criterios/evidencia y `verdict: "ACCEPTED"`. QA humano puede usar referencia recuperable a su revisión. El autor puede transcribir respuesta real, no inventarla. Cambiar candidato invalida prueba/QA.

verify rechaza aceptación con prueba fallida, salida ausente/alterada, candidato desactualizado o QA faltante/incompatible. **Solo verifica integridad documental, no autenticidad, independencia efectiva ni calidad semántica**: el revisor/Host conserva esa responsabilidad. Auditor no necesita tests ficticios: ACCEPTED significa informe suficiente dentro del alcance, nunca reparación ni producto certificado. RETAINED conserva motivo y candidato; no desbloquea integración.

## Comprobación y límites

`python3 -B -m unittest discover -s /ruta/framework/tests -v` incluye ciclo sintético rojo → candidato corregido → verde → referencia QA fixture → aceptación y rechazos negativos. QA del fixture es simulada explícitamente; no prueba calidad de un agente. `tests/test_dsh_skill_root.mjs` carga todos los cuerpos con servicios DSH instalados sin llamadas a modelos. Piloto humano pendiente: comprobar carga real de ambas entradas en Standard, permiso de lectura de producto hermano y revisión nativa de candidato. No afirmar esas propiedades por pasar tests locales.
