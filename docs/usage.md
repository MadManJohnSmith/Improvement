# Uso operativo del framework

## Dos capas: comprobada y objetivo 3.0

### Operación comprobada hoy

El MVP actual permite, bajo preparación supervisada:

- incorporación externa con `onboard.py`;
- carga nativa de skills;
- Auditoría completa/unitaria;
- Reparación continua acotada;
- candidato, QA, reauditoría, publicador, controlador, presupuesto y archivo;
- estados honestos `RETAINED`/`UNVERIFIED`.

### Objetivo C0–C7 (no implementado)

```bash
python3 -B scripts/bootstrap.py install --project /ruta/proyecto
```

El bootstrap llamará automáticamente a DSH Creator, generará modos/skills específicos, Creator invocará `accept`, el Host validará/backupeará/aceptará y activará o revertirá. El usuario no copiará prompts ni diseñará la prueba.

## Preparación operativa actual

Desde el framework:

```bash
python3 -B scripts/onboard.py \
  --project /ruta/producto \
  --workspace /ruta/workspace \
  --name proyecto \
  --prepare-skills \
  --session-root /ruta/padre

# revisar y repetir con --init
```

Repetición idéntica no escribe. Conflicto bloquea. `--update-skills` requiere autorización explícita y hace backup externo completo por skill antes de sustituir; no fusiona ni borra skills ajenas. Este backup operativo anterior no equivale todavía a la transacción generacional C4.

La raíz padre no debe tener un ancestro Git ambiguo ni ser mutable por terceros. Los enlaces gestionados sirven al loader; no conceden permisos ni crean sandbox.

## Uso actual con mensajes breves

Auditoría completa:

> Audita completamente este proyecto; no modifiques ni publiques.

Auditoría dirigida:

> Audita este flujo, característica o componente.

Reparación completa:

> Repara la cola autorizada en la rama o copia de prueba.

Reparación dirigida:

> Repara solo este hallazgo o componente.

El usuario no debe transportar recibos ni pedir la siguiente unidad. El Host coordina dentro del mandato. Si falta capacidad/permiso/evidencia, conserva `RETAINED` con causa y siguiente acción.

## Contrato mínimo actual de misión

`task.json` v1 registra:

- mode/objective/authorization_ref;
- root/files/base/change_scope;
- executor/criteria;
- commands/timeout/limits/exclusions.

`result.json` v1 enlaza:

- task hash;
- candidate file hashes;
- status/reason;
- findings;
- check y QA para repair.

Comprobaciones:

```bash
python3 -B scripts/missions.py run-check \
  --task /ruta/task.json \
  --output /ruta/check-1 \
  --timeout 60 -- /ruta/python -B test.py

python3 -B scripts/missions.py verify \
  --task /ruta/task.json \
  --result /ruta/result.json
```

`verify` prueba integridad documental, no autenticidad/semántica/autoridad. QA y Auditor posterior siguen siendo necesarios.

## Composición final 3.0

Los modos no serán presets universales. Creator producirá:

```text
<Proyecto>-auditor
<Proyecto>-continuous-repair
+ skills específicas justificadas
```

Capacidades internas de Creator y orden de reutilización aprobado:

```text
audit → discovery
scope → partición
architect → contratos
document → contexto durable
test → escenarios/holdouts
develop → generación
check → verify/review
debug → repair RETAINED
sync → drift/update
```

Los presets actuales son fixtures, no defaults.

## Actualización y backups 3.0

Antes de sustituir una skill/mode gestionado:

```text
comparar
→ backup completo
→ verificar backup
→ staging de conjunto
→ aceptación DSH
→ activar o rollback
```

Skill idéntica no escribe. Skill ajena/local edit bloquea. Creator no instala ni acepta.

## Seguridad

- Producto/framework read-only durante generación/auditoría.
- Reparación solo candidato/rama autorizada.
- Sin proveedor/modelo/routing nuevo desde artefactos.
- Sin secretos en prompts/argv/artefactos.
- Sin publicación remota implícita.
- No ejecutar scripts sugeridos por el producto sin autorización.
- Un estado declarativo `AUTHORIZED` no concede permiso.
- Falta de evidencia = `UNVERIFIED`, no PASS.

## Estado y próximos pasos

- Arquitectura: `../ARQUITECTURA_FLUJO_AGENTES.md` v3.0.
- Progreso: `../PLAN_IMPLEMENTACION.md` C0–C7.
- Evidencia: `status.md`.
- Contrato Creator: `creator-preset-spec.md`.
