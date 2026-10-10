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
import hashlib
import json
import os
import shutil
import sys
import tempfile

from pathlib import Path

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
REPAIR_TRIGGER = 'FAIL'
ROUNDS_DEFAULT = 2
# Las dos primeras rondas llevan nombre propio porque son las que el operador
# reconoce al leer el journal; a partir de ahí el nombre ya solo ordena.
ROUND_LABELS = ('pre', 'post')
AUDITOR_MARKERS = ('auditor',)
REPAIR_MARKERS = ('repar', 'repair')

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
# Reparar solo el candidato vigente

Repara únicamente los ítems del candidato registrado: su `candidate_head` y su
`candidate_diff_digest` son la identidad de lo que se está arreglando, y
cualquier otro árbol es una reparación que nadie pidió.

- No publiques, no commitees y no abras publicación remota: la candidata vive
  sucia y el Host decide.
- Nada se marca resuelto sin la salida que lo demuestra. Si el comando no
  corrió o no lo entiendes, el ítem sigue abierto.
- Registra los resultados de verificación en `mode-state/verification-results.jsonl`
  mediante el plugin. NUNCA en `evidence/`.
- Escribe el resultado en `evidence/campana/` con el nombre que indica tu
  `result_contract`, incluyendo la identidad real del candidato (head y digest
  de diff) tal y como la registraste.
"""


class CampaignPlanError(ValueError):
    """El plan no se puede generar con lo recibido; nada se escribe."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _document(value):
    return _canonical(value) + b'\n'


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


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
                  python=None, script=None):
    """Documento de plan v1 exacto, sin escribir nada en disco."""
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
         'result_contract': {'path': AUDIT_RESULT, 'evidence_name': EVIDENCE_NAME}},
    ]
    for index in range(1, rondas_max + 1):
        label = _round_label(index)
        verifier = 'verificar-' + label
        steps.append({'id': verifier, 'type': 'gate',
                      'command': _gate_command(workspace, python, script, label),
                      'on_fail': {'action': 'continue', 'rounds': 1}})
        steps.append({'id': 'reparar-%d' % index, 'type': 'ask', 'preset': repair,
                      'prompt_file': PROMPTS_DIRNAME + '/' + REPAIR_PROMPT,
                      'if_veredicto': {'from': verifier, 'path': VERDICT_NAME,
                                       'field': VERDICT_FIELD, 'equals': REPAIR_TRIGGER},
                      'result_contract': {'path': REPAIR_RESULT,
                                          'evidence_name': EVIDENCE_NAME}})
    steps.append({'id': 'verificar-final', 'type': 'gate',
                  'command': _gate_command(workspace, python, script, 'final'),
                  'on_fail': {'action': 'abort', 'rounds': 1}})
    steps.append({'id': 'cerrar', 'type': 'gate',
                  'command': _gate_command(workspace, python, script, 'cerrar'),
                  'on_fail': {'action': 'abort', 'rounds': 1}})
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
                digests[executable] = _sha256(path.read_bytes())
            except OSError as error:
                raise CampaignPlanError('ejecutable de gate ilegible: ' + executable) from error
        script_path = Path(step['command'][1])
        script_dir = script_path.parent
        for module in sorted(script_dir.glob('*.py')):
            if module.is_file() and not module.is_symlink():
                mod_str = str(module.resolve())
                if mod_str not in digests:
                    try:
                        digests[mod_str] = _sha256(module.read_bytes())
                    except OSError as error:
                        raise CampaignPlanError('módulo de gate ilegible: ' + mod_str) from error
    return digests


def manifest_document(plan_bytes, preset_ids, stacks, rondas_max, executables):
    """Manifiesto de la campaña: lo que el Host necesita para saber qué generó
    el plan. `workflow.py` no lo carga, así que puede llevar campos propios."""
    digest = _sha256(plan_bytes)
    return {
        'campaign_plan_sha256': digest,
        'generation': 'campana-' + digest[:16],
        'preset_ids': list(preset_ids),
        'rondas_max': rondas_max,
        'stacks': list(stacks),
        'executables': dict(executables),
    }


def prompts():
    return {AUDIT_PROMPT: AUDIT_PROMPT_TEXT, REPAIR_PROMPT: REPAIR_PROMPT_TEXT}


def generate(workspace, stack_value, preset_ids, *, rondas_max=ROUNDS_DEFAULT,
             python=None, script=None):
    """Devuelve plan, manifiesto y prompts ya serializados, sin tocar disco."""
    workspace = Path(workspace).resolve()
    plan = plan_document(workspace, preset_ids, rondas_max=rondas_max,
                         python=python, script=script)
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
        'prompts': {name: text.encode('utf-8') for name, text in prompts().items()},
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


def write_campaign(workspace, stack_value, preset_ids, *, rondas_max=ROUNDS_DEFAULT):
    """Escribe bytes privados solo cuando difieren; nunca toca generated/."""
    bundle = generate(workspace, stack_value, preset_ids, rondas_max=rondas_max)
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