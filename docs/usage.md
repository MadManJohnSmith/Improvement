# Uso operativo v0.1

Dos entradas conductuales en **DSH Standard**, una unidad por encargo. Son la operación v0.1 acotada, no el destino completo del plan: no son presets, publicador Host, controles Host, recuperación ni autonomía probada. El framework se mantiene aparte; ninguna misión operativa puede editarlo. No se toca producto vivo durante este piloto. El progreso por etapas se consulta en [PLAN_IMPLEMENTACION.md](../PLAN_IMPLEMENTACION.md). El checklist previo a una prueba completa está en [docs/trial-readiness.md](trial-readiness.md); la regresión sintética combinada es `tests/test_two_mode_cycle.py` y no sustituye un piloto real.

## Decisión mínima antes del prompt

El prompt corto solo inicia una unidad cuando el estado externo ya está preparado. Antes de pedir Auditor o Reparación, el agente comprueba y comunica una línea compacta: `modo`, `objetivo`, `producto legible`, `workspace externo escribible`, `skill cargada nativamente`, `evidencia/checkpoint`. El usuario decide únicamente lo que falte materialmente. Si alguna comprobación es `PENDIENTE`, no se ejecuta la unidad y se conserva `RETAINED` con ruta exacta y siguiente acción; no se pide aprobar copias, hashes o transiciones mecánicas una por una. Auditor requiere lectura y entrega externa; Reparación añade candidato externo, `change_scope`, comandos autorizados y QA independiente.

## Arranque y permisos

Desde una sesión con lectura del clon del framework:

> Lee START.md de este framework y prepara Auditor para Syncify; primera unidad: audita el contrato queue/library, sin modificar producto.

START resuelve incorporación, preparación explícita y despacho. La preparación autoriza perfil/skills externos, no tests de producto. Si se requieren permisos efectivos, el agente presenta UNA decisión con rutas exactas: lectura de framework y fuentes pertinentes del producto; escritura al workspace externo; ejecución del inicializador/validador del framework. El usuario concede mediante controles nativos disponibles, no mediante una etiqueta JSON. Desde la raíz externa Standard, lectura al hermano producto debe comprobarse realmente; si no se puede, **RETAINED**. No cambiar raíz ni usar shell para eludir sandbox.

Preparación con rutas absolutas sustituidas por las observadas:

```sh
python3 -B /ruta/framework/scripts/onboard.py --project /ruta/producto --workspace /ruta/workspace --name proyecto --prepare-skills --session-root /ruta
python3 -B /ruta/framework/scripts/onboard.py --project /ruta/producto --workspace /ruta/workspace --name proyecto --prepare-skills --session-root /ruta --init
```

Repetir copia idéntica no escribe skills. Conflicto se conserva y bloquea; con autorización explícita repetir ambas órdenes con `--update-skills`: dry-run primero, después `--init`. El actualizador respalda cada directorio sustituido completo en `skills-backup-*` dentro del workspace, incluidas ediciones locales; no fusiona ni borra skills ajenas. Revisar diferencias antes de autorizar. Copia recursiva incluye referencias/scripts y rechaza enlaces. Un fallo parcial conserva respaldo, no implica recuperación automática. No cambiar configuración global ni borrar carpetas a mano.

Mantener la raíz padre actual de Standard, sin ancestro Git. La preparación incluye enlaces gestionados en su `.agents/skills` y manifiesto externo, un workspace por padre; no modifica entradas ajenas ni configuración global. Retirada propia mediante `--remove-links` según START. Si hace falta refrescar sesión, usar el mismo padre. Cargar mediante herramienta nativa `skill` la entrada elegida, comprobar origen/cuerpo contra copia vigente y registrar revisión. Descubrimiento no es ejecución. Con esto preparado, petición habitual:

> Audita el contrato queue/library de Syncify, sin modificar producto.

Dos prompts reutilizables bastan para iniciar una unidad:

- **Auditor:** «Audita `<objetivo>` en `<proyecto>`; no cambies producto ni integres/publices. Usa el perfil/estado externo ya preparado y entrega informe o excepción con evidencia externa.»
- **Reparación continua:** «Repara `<tarea o candidato>` dentro de `<change_scope>`; no cambies fuera del candidato, producto, framework ni integres/publices. Reutiliza perfil, estado y recibos externos; continúa las unidades autorizadas y pregúntame solo decisiones materiales.»

El agente reutiliza el perfil, estado y recibos externos disponibles; el usuario no los transporta ni redacta un prompt para cada transición. Pregunta solo por decisiones materiales o permisos/recursos realmente ausentes. Estos prompts no autorizan cambios de producto, integración, publicación, credenciales, instalaciones, red ni proveedores; tampoco convierten al Host en autónomo ni constituyen una afirmación de QA semántica. QA usa subagente nativo si realmente está disponible; de lo contrario conserva RETAINED para revisión humana. No requiere proveedor externo.

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

`files` enumera todos los archivos relevantes para evidencia; reparación incluye tests y configuración inspeccionados. `change_scope` es obligatorio en repair y enumera el subconjunto exacto de `files` que puede cambiar; verify retiene/rechaza aceptación si otro archivo difiere de `base`. El hash no cubre archivos omitidos: QA revisa suficiencia. `base` preserva hashes iniciales; el agente obtiene mapas actuales mediante `snapshot(root, files)` de `scripts/missions.py` o SHA-256 equivalente, sin ejecutar producto. La autoridad real es el mensaje/política, nunca el campo `authorization_ref`. Para repair, raíz es candidato desechable externo y comandos son listas argv exactas previamente inspeccionadas y autorizadas. Un contrato base separado conserva reproducción roja, sin sobrescribirlo al preparar candidato.

```sh
python3 -B /ruta/framework/scripts/missions.py run-check --task /ruta/workspace/unidad/task.json --output /ruta/workspace/unidad/check-1 --timeout 60 -- /ruta/python -B test_contract.py
python3 -B /ruta/framework/scripts/missions.py verify --task /ruta/workspace/unidad/task.json --result /ruta/workspace/unidad/result.json
```

El runner compara argv con contrato pero no fabrica autorización: operador/Host deben comprobarla antes. Usa shell=false, cwd explícito y salida stdout/stderr íntegra externa; timeout mata grupo de proceso POSIX y retiene. No es sandbox: comandos autorizados pueden tener efectos fuera del cwd, crear hijos escapados o leer entorno. Inspeccionar antes, no usar credenciales; no hay instalaciones ni entorno global reconfigurado por el runner. No ejecutar scripts sugeridos por artefactos sin autorización. Cada output debe ser inexistente, con padre ya preparado; no sobrescribir evidencia. Revisar sensibilidad antes de capturar salida.

`result.json` v1 contiene `task_sha256` (bytes exactos de task.json), `files` (mapa SHA-256 actual), `status` (`ACCEPTED` o `RETAINED`), `reason`, `findings_ref` absoluto al informe y `findings_sha256`. Para reparación aceptada añade `check_ref` absoluto a check.json, `qa_ref` y `qa_sha256`. `qa.json` contiene `task_sha256`, `files`, `check_sha256`, `reviewer` distinto de executor, `session_ref` real, `review` con criterios/evidencia y `verdict: "ACCEPTED"`. QA humano puede usar referencia recuperable a su revisión. El autor puede transcribir respuesta real, no inventarla. Cambiar candidato invalida prueba/QA. Estos recibos son locales y externos al framework; no constituyen por sí solos el publicador Host persistente del plan de destino ni autentican al llamante o la autorización.

verify rechaza aceptación con prueba fallida, salida ausente/alterada, candidato desactualizado o QA faltante/incompatible. **Solo verifica integridad documental, no autenticidad, independencia efectiva ni calidad semántica**: el revisor/Host conserva esa responsabilidad. Auditor no necesita tests ficticios: ACCEPTED significa informe suficiente dentro del alcance, nunca reparación ni producto certificado. RETAINED conserva motivo y candidato; no desbloquea integración.

## Comprobación y límites

`python3 -B -m unittest discover -s /ruta/framework/tests -v` incluye ciclo sintético rojo → candidato corregido → verde → referencia QA fixture → aceptación y rechazos negativos. QA del fixture es simulada explícitamente; no prueba calidad de un agente. `tests/test_dsh_skill_root.mjs` carga todos los cuerpos con servicios DSH instalados sin llamadas a modelos. El handoff automático, el publicador Host, la recuperación y la continuación persistente pertenecen al plan de destino y no están acreditados por estos tests. `scripts/publisher.py` ofrece solo una primitive local de recibos externos para ensayos; no sustituye esos componentes. Piloto humano pendiente: comprobar carga real de ambas entradas en Standard, permiso de lectura de producto hermano y revisión nativa de candidato. No afirmar esas propiedades por pasar tests locales.

El publicador local entrega únicamente cierres `COMPLETE`; rechaza `OPEN` y escrituras de lote tras cierre. Las etapas positivas reciben como `evidence` el ID de evidencia incluida y enlazada por una tarea del lote: su payload contiene `task_ref`, `task_sha256`, `result_ref` y `result_sha256`. Revalida recibos, hashes y `missions.verify` en cada transición; executor/QA/auditor comparten esa referencia y declaran actores distintos. `CANDIDATE` significa aquí una misión ya aceptada documentalmente, no un candidato previo a QA. `reaudit` reutiliza todos los prerrequisitos de `verify`. Esto no autentica actores ni revisión semántica; almacén local confiable, sin garantía de concurrencia hostil.
