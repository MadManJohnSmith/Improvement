#!/usr/bin/env python3
"""Generador del plan de campaña: determinista y fail-closed (U6b).

El plan que sale de aquí lo carga `workflow.load_plan` sin una sola
transformación, así que el documento tiene que ser válido por construcción:
claves de primer nivel cerradas, pasos con tipos conocidos y todo ask con su
`prompt_file` y su `result_contract` resueltos antes de que exista el run dir.

Determinismo sin excusas: ni marcas de tiempo, ni identificadores de
ejecución, ni valores derivados del entorno que cambien entre dos generaciones
del mismo workspace. Dos generaciones seguidas producen los mismos bytes, y por
eso `campaign_plan_sha256` del manifiesto es el mismo sha256 que el Host
calcula sobre el plan verbatim.

Los ids de preset NO se deducen por convención de nombres: llegan verificados
desde la instalación (`transaction` los publica y el gate los comprueba contra
`agentPresets/list`). Un plan que nombrara un preset inexistente se abstendría
en el preflight, después de haber escrito todo esto.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mode_lifecycle import AUDIT_NEXT_PROMPT

import workflow_reasoning
from support import digest_bytes

CAMPAIGN_RELATIVE = '.dsh-managed/campaign'
PLAN_NAME = 'plan.json'
MANIFEST_NAME = 'manifest.json'
PROMPTS_DIRNAME = 'prompts'
AUDIT_PROMPT = 'auditar.md'
REPAIR_PROMPT = 'reparar.md'
# La campaña agrupa su evidencia bajo un único nombre: auditoría, reparaciones y
# veredictos comparten presupuesto de evidencia y se distinguen por fichero.
EVIDENCE_NAME = 'campana'
AUDIT_RESULT = 'auditoria.json'
REPAIR_RESULT = 'reparar.json'
VERDICT_NAME = 'veredicto.json'
VERDICT_FIELD = 'verdict'
ROUNDS_DEFAULT = 2
# Techos de lectura por intento ask, en tokens facturados por la sesión DSH
# (input + cacheRead + output; la cifra totalTokens que reporta cada
# petición). Tres corridas reales de auditar (11-17: 544.695 completada,
# 851.908 y 1.043.676 canceladas en techo con trabajo convergente — las dos
# cortadas estaban registrando hallazgos con workflow_write) muestran varianza
# de conducta ~2×: perseguir el máximo con +20% nunca converge, así que el
# margen se ensancha una vez con justificación (auditar +44% sobre el peor
# observado). reparar tiene tres muestras (521.780, 719.206, 1.021.579 —
# convergente, en la fase de cierre escribiendo registros; el estado acumulado
# se midió minúsculo, 6,7 KB, y auditar ya demostró que la distribución es
# ancha y no monótona: 545→852→1044→434): mismo régimen, techo simétrico al
# de auditar → 1.5M. A partir de
# aquí el techo es guarda-anti-bucle, no presupuesto exacto: una corrida que
# los supere ya no es varianza y la retención es la respuesta correcta.
# Referencia histórica: auditar 692k (11-14), reparar 401k legítimos (el 877k
# de reparar-2 fue re-verificación redundante que el techo corta), implementar
# 728k. El runner retiene con causa `ask-techo-tokens` citable; el techo solo
# sube si el reason lo dice (R2).
BUDGET_AUDIT_TOKENS = 1500000
BUDGET_REPAIR_TOKENS = 1500000
BUDGET_IMPLEMENT_TOKENS = 900000
# Las dos primeras rondas llevan nombre propio porque son las que el operador
# reconoce al leer el journal; a partir de ahí el nombre ya solo ordena.
ROUND_LABELS = ('pre', 'post')
AUDITOR_MARKERS = ('auditor',)
REPAIR_MARKERS = ('repar', 'repair')
IMPLEMENT_MARKERS = ('implement',)
IMPLEMENT_PROMPT = 'implementar.md'
IMPLEMENT_RESULT = 'implementation.json'
# Cada etapa declarada por el operador aterriza en un paso ask concreto. Un
# gate NUNCA recibe esfuerzo: la política de inferencia no le da autoridad.
STAGE_TO_STEP = {
    'auditoria': 'auditar',
    'implementacion': 'reparar',
    'verificacion': None,  # gate: la política de inferencia no le da autoridad
    'revision': None,       # gate: idem
}

AUDIT_PROMPT_TEXT = """\
# Auditar el producto desde tus propias observaciones

Audita ejecutando el entrypoint propio de cada stack declarado en el plan de
capacidades y citando su salida real. Nada se declara por inferencia: una
prueba que no has ejecutado no es una prueba.

- Un stack cuya capacidad falta se declara BLOCKED nombrando la capacidad que
  falta y su paso de provisión. Nunca PASS y nunca FAIL por no haber podido
  correr.
- Persiste cada hallazgo en `mode-state` con un ancla real (fichero y línea que
  has leído), mediante la herramienta de escritura del plugin.
- Copia `findings_persisted` literal del `count_command`: es el número que se
  registrará, no el que tú calculas.
- Los registros de verificación van a `mode-state/verification-results.jsonl`, a
  través del plugin. NUNCA a `evidence/`: ese ledger lo lee el gate y lo poda
  la instalación.
- No declares PASS por ausencia de evidencia. Sin evidencia el veredicto es
  BLOCKED y se nombra la pieza que falta.

Escribe el resultado de la auditoría en `evidence/campana/` con el nombre que
indica tu `result_contract`.
"""

REPAIR_PROMPT_TEXT = """\
# Reparar los hallazgos vivos de este workspace

Los hallazgos con ancla viven en `mode-state/findings.jsonl`. Si no hay ninguno
abierto, escribe el resultado diciéndolo y termina: una campaña sin hallazgos
no inventa trabajo.

- Reclama la sombra de reparación y registra el candidato en
  `mode-state/work-items.json`: `candidate_head` y `candidate_diff_digest` son
  la identidad de lo que se está arreglando; cualquier otro árbol es una
  reparación que nadie pidió.

- No publiques, no commitees y no abras publicación remota: la candidata vive
  sucia y el Host decide.
- Nada se marca resuelto sin la salida que lo demuestra. Si el comando no
  corrió o no lo entiendes, el ítem sigue abierto.
- Escribe el resultado en `evidence/campana/` con el nombre que indica tu
  `result_contract`, incluyendo la identidad real del candidato (head y digest
  de diff) tal y como la registraste.
"""


def _verification_records_block(stack_value):
    """El formato EXACTO de los registros de verificación, para el prompt.

    La campaña operativa del 2026-11-14 midió un turno de reparación que
    arregló los tres hallazgos y verificó de verdad, y el Host rechazó el
    ledger entero por la forma de los registros: el reparador no conocía el
    schema estricto que `stack.py` impone (cinco campos, sin extras) ni que el
    `command` debe ser el texto exacto del plan de capacidades. El schema
    correcto ya vive en el `state-schema.json` del mode-state; el prompt lo
    reproduce y lista los comandos exactos del stack para que no haya que
    buscarlos.
    """
    block = (
        "- Registra los resultados de verificación en "
        "`mode-state/verification-results.jsonl` mediante el plugin. NUNCA en "
        "`evidence/`. Formato EXACTO por registro (una línea JSONL por hallazgo "
        "verificado; ningún campo de más ni de menos — el Host rechaza el lote "
        "entero si un registro no cumple):\n"
        '  {"finding_id": "<id del hallazgo>", "candidate_head": "<head del '
        'candidato, 40-64 hex>", "candidate_diff_digest": "<digest del diff, 64 '
        'hex>", "result": "PASS" | "FAIL" | "BLOCKED", "command": <el comando '
        'de verificación de este stack, serializado EXACTAMENTE como abajo>}\n'
    )
    ready = [entry for entry in (stack_value or {}).get('stacks', [])
             if entry.get('verification_ready')]
    if ready:
        block += "- Comandos de verificación EXACTOS del plan de capacidades (la "                  "cadena `command` del registro es esta serialización JSON, byte "                  "a byte):\n"
        for entry in ready:
            command = entry.get('verify_command')
            exact = json.dumps(command, ensure_ascii=False,
                               separators=(',', ':'))
            block += f"  - {entry.get('stack')}: {exact}\n"
    return block


def _audit_handoff_block():
    """El contrato EXACTO del handoff de auditoría, para el prompt.

    Los audits de campaña improvisaron el handoff: el -6 aterrizó con un
    next_prompt derivado («no públicas» por «no publiques») que el count_command
    (filtro por prompt exacto) y el guarda del Host no podían ver, y toda
    campaña sobre la misma base se retuvo (issue #38). El prompt reproduce el
    contrato byte a byte, como hace el bloque de registros de verificación, para
    que el write no dependa de recordar la cadena ni de leerla del estado.
    """
    return (
        "- Persiste el handoff de la auditoría en `mode-state/handoffs.jsonl` "
        "mediante el plugin, después de los hallazgos y antes del resultado. "
        "Formato EXACTO del registro (una línea JSONL; ningún campo de más ni de "
        "menos — el plugin refusa un handoff que no cubra exactamente los "
        "hallazgos OPEN de la base, o que reescriba un handoff ya aterrizado con "
        "otro id):\n"
        '  {"handoff_id": "audit-complete-<base8>-<n>", "base_revision": "<base '
        '40-64 hex>", "finding_ids": [<los hallazgos OPEN de esa base>], '
        '"next_prompt": ' + json.dumps(AUDIT_NEXT_PROMPT, ensure_ascii=False) + "}\n"
        "- `next_prompt` es la cadena del contrato, no una frase tuya: cópiala "
        "byte a byte (arriba) tanto en el write como en el campo `next_prompt` "
        "del resultado. El plugin la normaliza al contrato y el count_command "
        "filtra por prompt exacto: un prompt derivado es un handoff que nadie "
        "puede contar y la campaña se retiene.\n"
    )


IMPLEMENT_PROMPT_TEXT = """\
# Implementar el cambio solicitado por el usuario

La candidata `kind=implement` la provisionó el Host y está registrada en
`mode-state/work-items.json` (path, branch `candidate`, base_revision,
request_sha256). Verifica su base contra la petición antes de tocar nada y
trabaja DENTRO de la candidata: el producto canónico queda intacto.

- Atiende EXACTAMENTE la petición de cambio que está al final de este prompt;
  nada más es trabajo tuyo.
- No publiques, no commitees y no abras publicación remota: la candidata vive
  sucia y el Host decide.
- La verificación usa el entrypoint propio del producto; un FAIL o BLOCKED
  nunca se reporta como PASS.
- Al terminar, actualiza la candidata en `mode-state/work-items.json`:
  `status` y `candidate_diff_digest` medidos sobre tus cambios, y `changed_paths`
  con lo que tocaste.
- Escribe el resultado en `{implementation_path}` (ese fichero exacto es lo
  que el runner valida; sin él el paso queda en fallo), con la identidad real
  del candidato y el estado de la petición (implementada / BLOCKED con la causa).

## Petición de cambio

{change_request}
"""


class CampaignPlanError(ValueError):
    """El plan no se puede generar con lo recibido; nada se escribe."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _document(value):
    return _canonical(value) + b'\n'


def _pick_preset(preset_ids, markers, role):
    """Primer id verificado que nombra el rol, en el orden recibido.

    El orden lo fija la instalación, no este generador: si nadie publica un
    preset con ese nombre, es que la pieza falta y se dice cuál."""
    for preset_id in preset_ids:
        if any(marker in preset_id for marker in markers):
            return preset_id
    raise CampaignPlanError(
        'ningún preset verificado nombra el rol %s (recibidos: %s)'
        % (role, ', '.join(preset_ids) or 'ninguno'))


def _round_label(index):
    if index <= len(ROUND_LABELS):
        return ROUND_LABELS[index - 1]
    return 'ronda-%d' % index


def _gate_command(workspace, python, script, phase):
    # El gate corre sin shell y con cwd en el workspace, así que el argv
    # necesita rutas absolutas: un nombre suelto no lo resuelve nadie.
    return [python, script, '--workspace', str(workspace), '--fase', phase]


def plan_document(workspace, preset_ids, *, rondas_max=ROUNDS_DEFAULT,
                  python=None, script=None, esfuerzos=None,
                  change_request=None):
    """Documento de plan v1 exacto, sin escribir nada en disco.

    Cada paso `ask` lleva su `budget_tokens` (techo de lectura fail-closed que
    el runner aplica en el sondeo; sin él el esquema estricto del workflow
    rechaza el plan). Desde la unidad del techo esto cambia los bytes del plan
    — y su digest — frente a versiones anteriores: los planes se regeneran al
    despachar campañas y no se compensa con trucos.

    `esfuerzos` es la política del operador por etapa de campaña
    (`workflow_reasoning.STAGES`). SIN opt-in no se añade ningún campo más:
    con opt-in, cada paso `ask` recibe `reasoning_effort` y los gates/joints
    no cambian en absoluto.
    """
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise CampaignPlanError('workspace inexistente: ' + str(workspace))
    if not isinstance(preset_ids, (list, tuple)) or not preset_ids:
        raise CampaignPlanError('hacen falta los ids de preset verificados')
    if any(not isinstance(preset_id, str) or not preset_id.strip()
           or len(preset_id) > 128 for preset_id in preset_ids):
        raise CampaignPlanError('preset_id inválido')
    if not isinstance(rondas_max, int) or isinstance(rondas_max, bool) or rondas_max < 1:
        raise CampaignPlanError('rondas_max debe ser entero >= 1')
    # Política de esfuerzo: solo etapas del vocabulario cerrado y solo si el
    # operador la pide explícitamente. Nivel o etapa desconocidos fallan antes
    # de generar nada, con el mismo error de dominio que el resto del plan.
    stage_efforts = {}
    if esfuerzos:
        try:
            stage_efforts = workflow_reasoning.stage_policy(esfuerzos)
        except workflow_reasoning.ReasoningError as error:
            raise CampaignPlanError(str(error)) from error
        unknown = set(stage_efforts) - set(STAGE_TO_STEP)
        if unknown:
            raise CampaignPlanError('etapas de esfuerzo desconocidas: '
                                    + ', '.join(sorted(unknown)))
        # Una etapa sin paso ask al que aterrizar no puede quedar en silencio:
        # el operador pidio una politica y el plan no la aplicaria en nada.
        unroutable = sorted(stage for stage, prefix in STAGE_TO_STEP.items()
                            if prefix is None and stage in stage_efforts)
        if unroutable:
            raise CampaignPlanError(
                'etapas sin paso ask al que aplicar el esfuerzo: '
                + ', '.join(unroutable))
    python = python or shutil.which('python3')
    script = script or str(Path(__file__).resolve().parent / 'campaign.py')
    if not python or not Path(python).is_absolute() or not Path(script).is_absolute():
        raise CampaignPlanError('gate requiere rutas absolutas del intérprete y campaign.py')
    python = str(Path(python).resolve())
    script = str(Path(script).resolve())
    auditor = _pick_preset(preset_ids, AUDITOR_MARKERS, 'auditor')
    repair = _pick_preset(preset_ids, REPAIR_MARKERS, 'reparación')
    steps = [
        {'id': 'preflight', 'type': 'gate',
         'command': _gate_command(workspace, python, script, 'preflight'),
         'on_fail': {'action': 'abort', 'rounds': 1}},
        {'id': 'auditar', 'type': 'ask', 'preset': auditor,
         'prompt_file': PROMPTS_DIRNAME + '/' + AUDIT_PROMPT,
         'result_contract': {'path': AUDIT_RESULT, 'evidence_name': EVIDENCE_NAME},
         'budget_tokens': BUDGET_AUDIT_TOKENS},
    ]
    for index in range(1, rondas_max + 1):
        label = _round_label(index)
        verifier = 'verificar-' + label
        steps.append({'id': verifier, 'type': 'gate',
                      'command': _gate_command(workspace, python, script, label),
                      'on_fail': {'action': 'continue', 'rounds': 1}})
        steps.append({'id': 'reparar-%d' % index, 'type': 'ask', 'preset': repair,
                      'prompt_file': PROMPTS_DIRNAME + '/' + REPAIR_PROMPT,
                      'result_contract': {'path': REPAIR_RESULT,
                                          'evidence_name': EVIDENCE_NAME},
                      'budget_tokens': BUDGET_REPAIR_TOKENS})
    steps.append({'id': 'verificar-final', 'type': 'gate',
                  'command': _gate_command(workspace, python, script, 'final'),
                  'on_fail': {'action': 'abort', 'rounds': 1}})
    steps.append({'id': 'cerrar', 'type': 'gate',
                  'command': _gate_command(workspace, python, script, 'cerrar'),
                  'on_fail': {'action': 'abort', 'rounds': 1}})
    if change_request:
        # El implementer atiende una petición de cambio del usuario: la
        # candidata kind=implement la provisiona el Host (gate) y la aceptación
        # del comportamiento la verifica el Host sobre la sombra. El ask solo
        # toca la candidata provisionada; el producto canónico queda intacto.
        implementer = _pick_preset(preset_ids, IMPLEMENT_MARKERS, 'implementador')
        steps.append({'id': 'provision-implement', 'type': 'gate',
                      'command': _gate_command(workspace, python, script,
                                               'provision-implement')
                                 + ['--request', change_request],
                      'on_fail': {'action': 'abort', 'rounds': 1}})
        steps.append({'id': 'implementar', 'type': 'ask', 'preset': implementer,
                      'prompt_file': PROMPTS_DIRNAME + '/' + IMPLEMENT_PROMPT,
                      'result_contract': {'path': IMPLEMENT_RESULT,
                                          'evidence_name': EVIDENCE_NAME},
                      'budget_tokens': BUDGET_IMPLEMENT_TOKENS})
        steps.append({'id': 'verificar-implement', 'type': 'gate',
                      'command': _gate_command(workspace, python, script,
                                               'verificar-implement')
                                 + ['--request', change_request],
                      'on_fail': {'action': 'abort', 'rounds': 1}})
    for stage, prefix in STAGE_TO_STEP.items():
        if prefix is None or stage not in stage_efforts:
            continue
        for step in steps:
            if step['type'] == 'ask' and (step['id'] == prefix
                                          or step['id'].startswith(prefix + '-')):
                # Precedencia paso > plan: el nivel de la etapa queda en el
                # paso, nunca en el plan, para que la campaña quede explícita.
                step['reasoning_effort'] = stage_efforts[stage]
    return {'schema_version': 1, 'name': 'campana-' + workspace.name,
            'workspace': str(workspace), 'preset': preset_ids[0], 'steps': steps}


def _declared_stacks(stack_value):
    """Nombres del plan de capacidades ya verificado por el Host."""
    return sorted({entry['stack'] for entry in stack_value['stacks']
                   if isinstance(entry.get('stack'), str)})


def _executable_digests(plan):
    """Vincula cada gate y sus módulos hermanos a los bytes que el Host ejecutaría realmente."""
    digests = {}
    for step in plan['steps']:
        if step['type'] != 'gate':
            continue
        for executable in step['command'][:2]:
            if executable in digests:
                continue
            path = Path(executable)
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise CampaignPlanError('ejecutable de gate no es fichero regular: ' + executable)
            try:
                digests[executable] = digest_bytes(path.read_bytes())
            except OSError as error:
                raise CampaignPlanError('ejecutable de gate ilegible: ' + executable) from error
        script_path = Path(step['command'][1])
        script_dir = script_path.parent
        for module in sorted(script_dir.glob('*.py')):
            if module.is_file() and not module.is_symlink():
                mod_str = str(module.resolve())
                if mod_str not in digests:
                    try:
                        digests[mod_str] = digest_bytes(module.read_bytes())
                    except OSError as error:
                        raise CampaignPlanError('módulo de gate ilegible: ' + mod_str) from error
    return digests


def manifest_document(plan_bytes, preset_ids, stacks, rondas_max, executables):
    """Manifiesto de la campaña: lo que el Host necesita para saber qué generó
    el plan. `workflow.py` no lo carga, así que puede llevar campos propios."""
    digest = digest_bytes(plan_bytes)
    return {
        'campaign_plan_sha256': digest,
        'generation': 'campana-' + digest[:16],
        'preset_ids': list(preset_ids),
        'rondas_max': rondas_max,
        'stacks': list(stacks),
        'executables': dict(executables),
    }


def prompts(stack_value=None, change_request=None):
    repair = (REPAIR_PROMPT_TEXT
              + _verification_records_block(stack_value))
    implement = (IMPLEMENT_PROMPT_TEXT
                 .replace('{registro_prompt}',
                          _verification_records_block(stack_value).rstrip())
                 .replace('{implementation_path}',
                          f"evidence/{EVIDENCE_NAME}/{IMPLEMENT_RESULT}")
                 .replace('{change_request}', change_request or '(sin petición)'))
    return {AUDIT_PROMPT: AUDIT_PROMPT_TEXT + _audit_handoff_block(),
            REPAIR_PROMPT: repair,
            IMPLEMENT_PROMPT: implement}


def generate(workspace, stack_value, preset_ids, *, rondas_max=ROUNDS_DEFAULT,
             python=None, script=None, change_request=None):
    """Devuelve plan, manifiesto y prompts ya serializados, sin tocar disco."""
    workspace = Path(workspace).resolve()
    plan = plan_document(workspace, preset_ids, rondas_max=rondas_max,
                         python=python, script=script,
                         change_request=change_request)
    plan_bytes = _document(plan)
    if not isinstance(stack_value, dict) or not isinstance(stack_value.get('stacks'), list):
        raise CampaignPlanError('plan de capacidades inválido')
    manifest = manifest_document(plan_bytes, preset_ids,
                                 _declared_stacks(stack_value), rondas_max,
                                 _executable_digests(plan))
    return {
        'plan': plan,
        'plan_bytes': plan_bytes,
        'manifest': manifest,
        'manifest_bytes': _document(manifest),
        'prompts': {name: text.encode('utf-8')
                    for name, text in prompts(stack_value, change_request).items()},
        'workspace': workspace,
    }


def _managed_directory(path):
    if path.is_symlink():
        raise ValueError('directorio gestionado es symlink: ' + str(path))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('directorio gestionado es symlink: ' + str(path))


def _write_if_changed(path, data):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('fichero o directorio gestionado es symlink: ' + str(path))
    if path.is_file() and path.read_bytes() == data:
        return False
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('fichero o directorio gestionado es symlink: ' + str(path))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def write_campaign(workspace, stack_value, preset_ids, *, rondas_max=ROUNDS_DEFAULT,
                   change_request=None):
    """Escribe bytes privados solo cuando difieren; nunca toca generated/."""
    bundle = generate(workspace, stack_value, preset_ids, rondas_max=rondas_max,
                      change_request=change_request)
    root = bundle['workspace'] / CAMPAIGN_RELATIVE
    managed = root.parent
    prompts_dir = root / PROMPTS_DIRNAME
    for directory in (managed, root, prompts_dir):
        _managed_directory(directory)
    files = {root / PLAN_NAME: bundle['plan_bytes'],
             root / MANIFEST_NAME: bundle['manifest_bytes']}
    files.update({prompts_dir / name: data for name, data in bundle['prompts'].items()})
    # Preflight de todos los destinos antes de tocar cualquiera: no publicar
    # media campaña si otro fichero gestionado fue sustituido por un symlink.
    for path in files:
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('fichero o directorio gestionado es symlink: ' + str(path))
    written = False
    for path, data in files.items():
        written = _write_if_changed(path, data) or written
    return {'written': written,
            'campaign_plan_sha256': bundle['manifest']['campaign_plan_sha256'],
            'path': str(root / PLAN_NAME)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='campaign_plan.py',
        description='Genera el plan determinista de campaña para un workspace.')
    parser.add_argument('workspace')
    parser.add_argument('--preset', action='append', dest='presets', required=True,
                        metavar='ID', help='id de preset verificado (repetible)')
    parser.add_argument('--rondas', type=int, default=ROUNDS_DEFAULT,
                        help='pares verificar/reparar (por defecto %d)' % ROUNDS_DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        import stack as capability_plan
        outcome = write_campaign(arguments.workspace,
                                 capability_plan.load(arguments.workspace),
                                 arguments.presets, rondas_max=arguments.rondas)
    except (CampaignPlanError, OSError) as error:
        print('campaign_plan: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())