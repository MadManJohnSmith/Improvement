# Uso operativo del framework

El framework tiene dos capas con roles distintos:

1. **Flujo automático (capa 3.0, implementada y comprobada):** un comando coordina Creator, validación Host, backups, aceptación, activación y rollback. Es la experiencia de usuario final. Estado comprobado en [status.md](status.md).
2. **Herramientas de mantenimiento (base MVP):** scripts que el mantenedor usa para preparar ensayos, auditar cobertura y verificar misiones. No son la experiencia final ni defaults para proyectos nuevos.

## Requisito previo (una vez, del titular)

DSH instalado y configurado con al menos un proveedor/modelo. El framework no lee, copia ni pide API keys: la puerta de proveedor verifica estructura de configuración y nombres de variables, nunca valores. Si ninguna vía de autenticación funciona, el run queda recuperable con la causa y una acción concreta.

## Flujo automático: `bootstrap.py`

Genera e instala los modos y skills específicos del proyecto:

```bash
python3 -B scripts/bootstrap.py install \
  --project /ruta/proyecto \
  --launch-dsh
```

Qué hace:

1. preflight: descubre el proyecto, verifica DSH/proveedor y prepara un workspace externo limpio (`<Proyecto>-workspace/`);
2. prepara el run (`creator-runs/<generation-id>/`) con prompt versionado y snapshot de la biblioteca de skills;
3. despacha Creator: con `--launch-dsh` detiene instancias DSH previas, libera el puerto, arranca `dsh web` con el overlay del framework y supervisa la única sesión Creator (ligada al workspace, agrupada en la UI, sin delegación); sin esa opción reutiliza una instancia DSH autenticada existente;
4. Creator genera `<Proyecto>-auditor`, `<Proyecto>-continuous-repair` y skills específicas justificadas, seleccionando primero biblioteca base y catálogo;
5. Creator invoca `bootstrap accept`; el Host valida en 10 capas, respalda, instala en staging, ejecuta la aceptación determinista y publica los modos como presets de usuario en DSH, verificados vía `agentPresets/list` antes de `ACTIVE`;
6. activa el conjunto o hace rollback/RETAINED. Solo el Host emite `ACTIVE`.

El usuario no copia prompts, JSON, rutas, recibos ni escenarios de aceptación.

Otros subcomandos: `accept` (solo lo invoca Creator), `verify-acceptance` y `finalize` (etapas de aceptación Host), `update` (regeneración por cambio material), `uninstall` y `purge-data`. Repetir `install` sobre un run reanudable reanuda el despacho; sobre un run propiedad del Host lo informa sin re-despachar.

### Estados de run

```text
CREATED → GENERATING → GENERATED → VALIDATING → BACKED_UP → STAGED → ACCEPTING → ACTIVE
                                    └→ RETAINED (con causa y acción concreta) → ROLLED_BACK → RECOVERY_REQUIRED
```

Sin sesión DSH autenticada el run queda `CREATED`/`PREPARED` recuperable; nunca en un estado silencioso. Una escritura denegada o un conflicto de esquema durante la generación es un hallazgo que se reporta, nunca un motivo de escalada de permisos: el workspace del run es escribible en el modo vigente y el Creator no envía nunca `sandbox_permissions` ni `justification`.

### Operación de los modos generados

Con `<Proyecto>-auditor` y `<Proyecto>-continuous-repair` activos, la operación es por mensajes breves en el proyecto:

- Auditar completo: «Audita completamente este proyecto; no modifiques ni publiques.»
- Auditar un área: «Audita este flujo, característica o componente.»
- Reparar todo lo persistido: «Repara los hallazgos de la auditoría; no publiques.»
- Reparar IDs: «Repara A-01 y M-02; no publiques.»

Al seleccionar un preset, su primera acción debe cargar el skill exacto homónimo. Auditor persiste un handoff acotado en `<Proyecto>-workspace/mode-state`. Repair deriva un worktree hermano mediante digest de revisión base completa e IDs seleccionados, ejecuta checks cerrados de path/symlink/worktree/branch/HEAD/dirty/stale/collision y modifica/prueba solo mediante bash con workdir candidato. El prompt simple no autoriza commit: deja árbol sucio o patch y `candidate_commit: null`; un commit requiere otro prompt explícito. Drift de HEAD/status canónicos o diff fuera del candidato produce `RETAINED` sin más acción. Esto es enforcement contractual con regresiones, no aislamiento mecánico; no hay CAS/lease multiarchivo.

### Qué significa "verificado"

Repair solo puede registrar como evidencia el comando que el propio proyecto declara, y ese
comando lo fija el Host al instalar en `<Proyecto>-workspace/.dsh-managed/capability-plan.json`:

```bash
python3 -B scripts/bootstrap.py stack --project /ruta/proyecto --workspace /ruta/proyecto-workspace
```

Imprime una línea por stack detectado. `listo` significa que el comando se puede ejecutar
tal cual. `falta <capacidad>` significa que hace falta algo concreto y el plan dice
exactamente cómo instalarlo, siempre fuera del producto.

Dos propiedades de ese plan que conviene conocer:

- **El comando se nombra como se puede ejecutar.** Si tu toolchain está fuera del `PATH` por
  defecto (un SDK de Flutter en `~/.local/share`, un JDK en `/opt`), el plan lo nombra por
  su ruta absoluta o por la copia local del workspace. Un nombre suelto que la shell del
  reparador no resuelve convertiría una suite que funciona en un `BLOCKED` injusto.
- **El sandbox decide qué se puede escribir.** `workspace-write` solo deja escribir en el
  árbol de la sesión. Un SDK que se reescribe a sí mismo en cada ejecución (Flutter sella su
  versión de engine en `bin/cache` en cada llamada) necesita una copia local: por eso el plan
  pide materializarla en `<workspace>/.stack/<stack>/` con enlaces duros, que no cuestan
  espacio y no tocan tu instalación original.

Cuando algo no puede ejecutarse, el registro es `BLOCKED` nombrando la capacidad y su paso de
provisión. Nunca hay un `PASS` inventado ni un sustituto escrito a mano: un mock o una copia
del código del producto sirven para investigar, no para verificar.

### Integración y recuperación de espacio (operador)

El prompt simple no autoriza commit: el operador integra y después retira la candidata. Tras `git merge --ff-only <rama-dsh>` y `git push` en la rama canónica:

1. Registrar `INTEGRATED` en `work-items.json.candidate` (solo el Host u el operador puede; los modos conservan el registro anterior y no lo borran).
2. Retirar el worktree de esa candidata: `python3 -B scripts/bootstrap.py state --project <ruta-del-producto> --retire`. El comando hace el `git worktree remove` y el `git branch -D` **solo** si comprueba que la candidata está `INTEGRATED`, que su cabeza está en la rama canónica, que el worktree registrado es el suyo y coincide con la registrada, y que está limpio; si algo falla, no borra nada y dice por qué. Es idempotente: repetirlo informa de que ya no hay worktree ni rama.

El paso 2 no es cosmético: cada candidata puede acarrear decenas de GB de artefactos de compilación y varias rondas seguidas agotan el disco, lo que corta DSH a mitad de un turno. Comprobado en el piloto de Syncify, donde cuatro candidatas integradas sumaban unos 320 GB y el disco lleno tumbó dos turnos de Repair.

### Cuando el estado y el repositorio dejan de contarse (operador)

El mismo comando sin `--retire` ni `--repoint` es un informe, no modifica nada:

```bash
python3 -B scripts/bootstrap.py state --project <ruta-del-producto>
```

Nombra tres discrepancias que el estado por sí solo no puede ver:

- la cabeza integrada que una reescritura de historia (`commit --amend`, `rebase`, push forzado) ya no dejó en la rama canónica, con `integrated_head_rewritten` y la revisión actual; para corregir el registro a mano, `--repoint <revisión>`, que solo acepta una revisión que git pruebe ancestro del HEAD canónico con el producto limpio y deja recibo en `overflows.jsonl`;
- los hallazgos que el ledger sigue llamando `OPEN` aunque su work item sea `VERIFIED` (`closed_findings`): el hallazgo pasa a `RESOLVED` cuando una auditoría posterior observa el arreglo, así que entre ambas cosas la cola ofrece trabajo ya hecho;
- los hallazgos `OPEN` que ningún handoff tomó nunca (`uncovered_findings`).

## Herramientas de mantenimiento (capa MVP)

Para mantenimiento del framework o pilotos controlados supervisados por el mantenedor.

### Preparación de un ensayo con `onboard.py`

Clona el framework junto al proyecto, nunca dentro:

```text
padre/
├── Improvement/            # framework (este repo)
├── proyecto/
└── proyecto-workspace/
```

```bash
python3 -B scripts/onboard.py \
  --project /ruta/proyecto \
  --workspace /ruta/proyecto-workspace \
  --name mi-proyecto \
  --prepare-skills \
  --session-root /ruta/padre

# revisar el dry-run y repetir con --init
```

Repetición idéntica no escribe. Conflicto bloquea. `--update-skills` requiere autorización explícita y hace backup externo completo por skill antes de sustituir; no fusiona ni borra skills ajenas. Este backup operativo no equivale a la transacción generacional de la capa 3.0.

La raíz padre no debe tener un ancestro Git ambiguo ni ser mutable por terceros. Los enlaces gestionados sirven al loader de skills; no conceden permisos ni crean sandbox. Un workspace por padre.

### Cobertura de auditoría con `audit.py`

`inventory` y `consolidate` comprueban inventario, partición y estados declarados; no son un auditor semántico ni un control de permisos. Contrato completo en [audit-contract.md](audit-contract.md).

### Verificación documental de misiones con `missions.py`

`task.json` v1 registra mode/objective/authorization_ref, root/files/base/change_scope, executor/criteria y commands/timeout/limits/exclusions; `result.json` v1 enlaza task hash, hashes de candidato, status/reason, findings y check/QA para repair:

```bash
python3 -B scripts/missions.py run-check \
  --task /ruta/task.json --output /ruta/check-1 \
  --timeout 60 -- /ruta/python -B test.py

python3 -B scripts/missions.py verify \
  --task /ruta/task.json --result /ruta/result.json
```

`verify` prueba integridad documental, no autenticidad/semántica/autoridad. QA y auditor posterior siguen siendo necesarios.

## Qué no hacer

- No cargar ni recrear presets/modos genéricos eliminados (permanecen solo en Git).
- No presentar Standard ni los presets de Syncify/RehabWeb como experiencia final: son fixtures.
- No usar shell/cwd/enlaces para eludir permisos.
- No modificar el framework durante una misión operativa; las propuestas se devuelven o se aplican en una misión de mantenimiento separada.
- No publicar ni integrar sin mandato del titular.

## Seguridad

- Producto y framework read-only durante generación y auditoría; reparación solo en candidato/rama autorizada.
- Sin proveedores/modelos/routing nuevos desde artefactos; sin secretos en prompts/argv/artefactos.
- Sin publicación remota implícita; no ejecutar scripts sugeridos por el producto sin autorización.
- Un estado declarativo `AUTHORIZED` no concede permiso. Falta de evidencia = `UNVERIFIED`, no PASS.
- Configurar un proveedor en DSH no autoriza al framework a leer su API key.

## Referencias

- Arquitectura normativa: [`ARQUITECTURA_FLUJO_AGENTES.md`](../ARQUITECTURA_FLUJO_AGENTES.md)
- Contrato generacional de Creator: [creator-preset-spec.md](creator-preset-spec.md)
- Preparación DSH: [setup-dsh.md](setup-dsh.md)
- Estado comprobado: [status.md](status.md)
- Cambios: [`CHANGELOG.md`](../CHANGELOG.md)
