#!/usr/bin/env python3
"""Ejecutor de planes de workflow sin DSH: pasos gate/join/fase con journal encadenado.

Reglas del plan aprobado (U1):
- Plan JSON validado fail-closed (ids únicos, depends previos y acíclicos por
  construcción, tipos conocidos, estructura por tipo). Un plan inválido
  produce error sin crear journal ni directorio de ejecución.
- Directorio de ejecución externo al producto: hermano del workspace
  `<workspace>-workflow/<run_id>/`, con modo 0700 (patrón de
  host_controller.py). Jamás dentro del workspace ni de un mode-state: el
  preflight de mode-state archiva y borra ficheros ajenos.
- El run_id se deriva del contenido verbatim del plan
  (`r-<sha256[:24]>`): re-ejecutar el mismo plan reanuda el mismo run dir.
- Journal append-only `journal.jsonl` con digest de contenido encadenado y
  punto de control atómico `head.json` (patrón exacto de scripts/metrics.py):
  registro <= 4096 B, almacén <= 8 MiB (tope inyectable para pruebas); lo
  excedido produce RUN_RETAINED y NUNCA se trunca. Los intentos rechazados
  son registros de primera clase: no se borran ni se editan.
- Reanudación por replay: un paso se salta solo con STEP_COMPLETED verificado
  (sha256 del fichero de observación en disco igual al digest registrado).
- `plan.snapshot.json` es copia verbatim del plan; su sha256 va en el
  registro PLAN_LOADED y se cotea en cada reanudación y en verify.
- Gates: argv sin shell, cwd en el workspace, salida capturada a un fichero
  de observación `observations/NN-<step>-<intent>.json`. Reciben
  WORKFLOW_OBSERVATION con la ruta del resultado del ask previo cuando
  existe (en U1 ningún ask llega a ejecutarse). Exit 0 = PASS, exit 1 = FAIL
  enrutable según on_fail (retry/abort/continue con rounds), otro exit o
  fallo de spawn = IMPOSSIBLE -> RETAINED.
- Fase: cuenta GATE_REJECTED desde su PHASE_STARTED; exceder max_rounds
  retiene. Join: barrera sobre depends completados, con digest de cada dep.
- Salidas: RUN_COMPLETED (exit 0), RUN_RETAINED con causa (exit 1) y
  ABSTENCIÓN para plan con ask sin cliente o sin preset verificado (nada
  hecho, nada escrito, sin run dir; exit 1).
- Paso ask (U3): cliente DSH por la vía no-launch (sesiones existentes;
  JAMÁS lanza dsh web), sesión NUEVA por intento con el preset verificado
  del proyecto (agentPresets/list + read con composición operativa exacta
  incl. ./anti-escalation.mjs; nunca sesiones ajenas), request_id
  determinista sha256(run_id, step_id, attempt), poll con quiescencia
  transitiva fail-closed (hijos/jobs malformados bloquean; patrón
  acceptance_reviewer), deadline -> cancel_session + gracia 30 s y
  RETAINED sin quiescencia confirmada. La observación es el texto del
  asistente del turno correlacionado (extensión local del folding, que
  solo consumía turn/start-end): texto completo en observations/ y al
  journal solo digests. Reanudación [corr-3]: la sesión viva de un
  intento sin terminal recibe el MISMO request_id o se re-observa su
  transcript; sesión perdida -> RETAINED, nunca re-despacho a sesión
  nueva. Errores de red/transporte (ValueError, OSError, URLError) se
  convierten en RUN_RETAINED con causa: nunca una excepción sin
  retención. Con result_contract, la sesión escribe el resultado
  estructurado en <workspace>/evidence (única raíz legal) y el runner
  valida y registra su digest.

Solo biblioteca estándar de Python; un solo escritor por run dir.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error

from pathlib import Path

from composition_contract import (ANTI_ESCALATION_PLUGIN,
                                  PROHIBITED_MODE_PLUGIN_TERMS,
                                  REQUIRED_MODE_PLUGINS)

MAX_RECORD = 4096
MAX_STORE = 8 * 1024 * 1024
MAX_PLAN_BYTES = 128 * 1024
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_PROMPT_BYTES = 262144
MAX_RESULT_BYTES = 1024 * 1024
ASK_POLL_SECONDS = 0.1
ASK_CANCEL_GRACE_SECONDS = 30.0
# Reserva que garantiza que RUN_RETAINED quepa cuando un registro regular
# ya no cabe; el apéndice terminal solo exige caber sin reserva.
RETAINED_RESERVE = 512
GENESIS = '0' * 64
JOURNAL_NAME = 'journal.jsonl'
HEAD_NAME = 'head.json'
SNAPSHOT_NAME = 'plan.snapshot.json'
OBSERVATIONS_NAME = 'observations'
HEAD_KIND = 'workflow-head'
CONTENT_KEYS = ('version', 'seq', 'event_id', 'kind', 'payload', 'prev_sha256')
ENVELOPE_KEYS = frozenset(CONTENT_KEYS) | {'content_sha256'}
KINDS = frozenset({'PLAN_LOADED', 'PHASE_STARTED', 'STEP_STARTED', 'STEP_COMPLETED',
                   'GATE_REJECTED', 'STEP_FAILED', 'ROUND_CAP_REACHED', 'RUN_RETAINED',
                   'RUN_COMPLETED'})
STEP_TYPES = ('gate', 'join', 'fase', 'ask')
FAIL_ACTIONS = ('retry', 'abort', 'continue')
STEP_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
OBSERVATION_RE = re.compile(r'^observations/[0-9]{2,}-[A-Za-z0-9._-]{1,80}-(gate|join|ask)\.json$')
OBS_NUMBER_RE = re.compile(r'^([0-9]+)-')
TOP_KEYS = frozenset({'schema_version', 'name', 'workspace', 'run_root', 'preset', 'steps'})
REQUIRED_TOP = ('schema_version', 'name', 'workspace', 'steps')


class WorkflowError(ValueError):
    """Fallo cerrado de validación o integridad; no es un resultado de ejecución."""


class _StoreFull(Exception):
    """El almacén alcanzaría su tope; el llamante retiene sin truncar."""


class _RecordTooLarge(Exception):
    """El registro excedería 4096 B; se retiene sin truncarlo."""


class _Retained(Exception):
    """Fin de ejecución con causa de retención ya registrada (si cupo)."""

    def __init__(self, cause):
        super().__init__(cause)
        self.cause = cause


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------- plan

def load_plan(plan_path):
    """Carga y valida el plan; falla cerrada sin efecto secundario alguno."""
    try:
        raw = Path(plan_path).read_bytes()
    except OSError as error:
        raise WorkflowError('plan ilegible: ' + str(error)) from error
    if len(raw) > MAX_PLAN_BYTES:
        raise WorkflowError('plan demasiado grande (> ' + str(MAX_PLAN_BYTES) + ' B)')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise WorkflowError('plan no es UTF-8 válido') from error
    try:
        value = json.loads(text)
    except ValueError as error:
        raise WorkflowError('plan JSON ilegible: ' + str(error)) from error
    plan = _validate_plan(value)
    _load_ask_prompts(plan, Path(plan_path).resolve().parent)
    return plan, raw


def _load_ask_prompts(plan, plan_dir):
    """Resuelve prompt_file de cada ask relativo al directorio del plan;
    falla cerrada antes de crear run dir."""
    for step in plan['steps']:
        if step['type'] != 'ask' or step['prompt_file'] is None:
            continue
        path = plan_dir / step['prompt_file']
        try:
            data = path.read_bytes()
        except OSError as error:
            raise WorkflowError('prompt_file ilegible: ' + str(error)) from error
        if len(data) > MAX_PROMPT_BYTES:
            raise WorkflowError('prompt_file demasiado grande (> ' + str(MAX_PROMPT_BYTES) + ' B)')
        try:
            step['prompt'] = data.decode('utf-8')
        except UnicodeDecodeError as error:
            raise WorkflowError('prompt_file no es UTF-8 válido: ' + str(path)) from error


def _validate_plan(value):
    if not isinstance(value, dict):
        raise WorkflowError('plan inválido: se esperaba un objeto JSON')
    unknown = set(value) - TOP_KEYS
    if unknown:
        raise WorkflowError('plan inválido: claves desconocidas: ' + ', '.join(sorted(unknown)))
    missing = [key for key in REQUIRED_TOP if key not in value]
    if missing:
        raise WorkflowError('plan inválido: faltan claves: ' + ', '.join(missing))
    if not _is_int(value['schema_version']) or value['schema_version'] != 1:
        raise WorkflowError('plan inválido: schema_version debe ser 1')
    name = value['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 128:
        raise WorkflowError('plan inválido: name requerido (string <= 128)')
    if not isinstance(value['workspace'], str) or not value['workspace'].strip():
        raise WorkflowError('plan inválido: workspace requerido')
    workspace = Path(value['workspace']).resolve()
    if not workspace.is_dir():
        raise WorkflowError('plan inválido: workspace inexistente: ' + str(workspace))
    run_root = None
    if value.get('run_root') is not None:
        raw_root = value['run_root']
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise WorkflowError('plan inválido: run_root inválido')
        run_root = _resolve_run_root(workspace, raw_root)
    preset = value.get('preset')
    if preset is not None and (not isinstance(preset, str) or not preset.strip() or len(preset) > 128):
        raise WorkflowError('plan inválido: preset inválido')
    raw_steps = value['steps']
    if not isinstance(raw_steps, list) or not raw_steps:
        raise WorkflowError('plan inválido: steps debe ser una lista no vacía')
    steps = []
    previous_ids = set()
    for index, raw_step in enumerate(raw_steps):
        step = _validate_step(raw_step, previous_ids, index)
        steps.append(step)
        previous_ids.add(step['id'])
    return {'name': name, 'workspace': workspace, 'run_root': run_root,
            'preset': preset, 'steps': steps}


def _validate_step(raw, previous_ids, index):
    where = ' (paso ' + str(index) + ')'
    if not isinstance(raw, dict):
        raise WorkflowError('paso inválido: se esperaba un objeto' + where)
    unknown = set(raw) - {'id', 'type', 'depends', 'command', 'on_fail',
                          'name', 'max_rounds', 'prompt', 'prompt_file', 'timeout_s',
                          'result_contract'}
    if unknown:
        raise WorkflowError('paso inválido: claves desconocidas: ' + ', '.join(sorted(unknown)) + where)
    step_id = raw.get('id')
    if not isinstance(step_id, str) or not STEP_ID_RE.match(step_id):
        raise WorkflowError('paso inválido: id requerido '
                            '([A-Za-z0-9][A-Za-z0-9._-]{0,63})' + where)
    if step_id in previous_ids:
        raise WorkflowError('paso inválido: id duplicado: ' + step_id)
    step_type = raw.get('type')
    if step_type not in STEP_TYPES:
        raise WorkflowError('paso inválido: tipo desconocido: ' + repr(step_type) + where)
    depends = raw.get('depends')
    if depends is None:
        depends = []
    if not isinstance(depends, list) or any(not isinstance(dep, str) for dep in depends):
        raise WorkflowError('paso inválido: depends debe ser una lista de ids' + where)
    if len(set(depends)) != len(depends):
        raise WorkflowError('paso inválido: depends repetidos' + where)
    for dep in depends:
        if not STEP_ID_RE.match(dep):
            raise WorkflowError('paso inválido: id de dependencia inválido: ' + repr(dep) + where)
        if dep not in previous_ids:
            raise WorkflowError('paso inválido: dependencia no previa: ' + dep + where)
    step = {'id': step_id, 'type': step_type, 'depends': tuple(depends)}
    if step_type == 'gate':
        command = raw.get('command')
        if (not isinstance(command, list) or not command
                or any(not isinstance(part, str) or not part for part in command)):
            raise WorkflowError('paso inválido: command debe ser argv no vacío de strings' + where)
        on_fail = raw.get('on_fail')
        if not isinstance(on_fail, dict) or set(on_fail) - {'action', 'rounds'} or 'action' not in on_fail:
            raise WorkflowError('paso inválido: on_fail requiere action' + where)
        action = on_fail['action']
        if action not in FAIL_ACTIONS:
            raise WorkflowError('paso inválido: action desconocida: ' + repr(action) + where)
        rounds = on_fail.get('rounds')
        if rounds is not None and (not _is_int(rounds) or rounds < 1):
            raise WorkflowError('paso inválido: rounds debe ser entero >= 1' + where)
        if action == 'retry' and rounds is None:
            raise WorkflowError('paso inválido: retry requiere rounds >= 1' + where)
        step['command'] = list(command)
        step['on_fail'] = {'action': action, 'rounds': rounds}
    elif step_type == 'join':
        if not depends:
            raise WorkflowError('paso inválido: join requiere depends' + where)
    elif step_type == 'fase':
        phase_name = raw.get('name')
        if not isinstance(phase_name, str) or not phase_name.strip() or len(phase_name) > 128:
            raise WorkflowError('paso inválido: fase requiere name' + where)
        max_rounds = raw.get('max_rounds')
        if max_rounds is not None and (not _is_int(max_rounds) or max_rounds < 1):
            raise WorkflowError('paso inválido: max_rounds debe ser entero >= 1' + where)
        step['name'] = phase_name
        step['max_rounds'] = max_rounds
    else:  # ask
        prompt = raw.get('prompt')
        prompt_file = raw.get('prompt_file')
        if (prompt is None) == (prompt_file is None):
            raise WorkflowError('paso inválido: ask requiere prompt o prompt_file (excluyentes)' + where)
        if prompt is not None and (not isinstance(prompt, str) or not prompt):
            raise WorkflowError('paso inválido: prompt inválido' + where)
        if prompt_file is not None and (not isinstance(prompt_file, str) or not prompt_file):
            raise WorkflowError('paso inválido: prompt_file inválido' + where)
        timeout = raw.get('timeout_s', 1800)
        if not _is_int(timeout) or timeout < 1:
            raise WorkflowError('paso inválido: timeout_s debe ser entero >= 1' + where)
        contract = raw.get('result_contract')
        if contract is not None:
            if not isinstance(contract, dict) or set(contract) != {'path'}:
                raise WorkflowError('paso inválido: result_contract requiere exactamente path' + where)
            rel = contract['path']
            if (not isinstance(rel, str) or not rel.strip() or Path(rel).is_absolute()
                    or '..' in Path(rel).parts):
                raise WorkflowError('paso inválido: result_contract.path debe ser relativo '
                                    'sin escape' + where)
        step['prompt'] = prompt
        step['prompt_file'] = prompt_file
        step['timeout_s'] = timeout
        step['result_contract'] = None if contract is None else {'path': contract['path']}
    return step


def _default_run_root(workspace):
    return workspace.parent / (workspace.name + '-workflow')


def _resolve_run_root(workspace, raw):
    """run_root resuelto y fail-closed: fuera del workspace y de un mode-state
    (el preflight de mode-state archiva y borra ficheros ajenos)."""
    root = Path(raw).resolve()
    if root == workspace or workspace in root.parents:
        raise WorkflowError('run_root dentro del workspace: ' + str(root))
    if 'mode-state' in root.parts:
        raise WorkflowError('run_root no puede residir en un mode-state')
    return root


def _run_id_for(plan_sha256):
    return 'r-' + plan_sha256[:24]


# ------------------------------------------------------------- journal

def _checkpoint(run_dir):
    head = run_dir / HEAD_NAME
    if not head.is_file():
        raise WorkflowError('journal incompleto: falta head.json')
    raw = head.read_bytes()
    if len(raw) > MAX_RECORD:
        raise WorkflowError('punto de control demasiado grande')
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise WorkflowError('punto de control ilegible') from error
    if (not isinstance(value, dict) or set(value) != {'kind', 'version', 'events', 'head_sha256'}
            or value.get('kind') != HEAD_KIND or value.get('version') != 1
            or not _is_int(value.get('events')) or value['events'] < 0
            or not isinstance(value.get('head_sha256'), str)):
        raise WorkflowError('punto de control inválido')
    return {'events': value['events'], 'head': value['head_sha256']}


def _validate_payload(kind, payload, where):
    if not isinstance(payload, dict):
        raise WorkflowError('payload de evento inválido' + where)

    def exact(*keys):
        if set(payload) != set(keys):
            raise WorkflowError('payload inválido para ' + kind + where)

    def need_text(key, maxlen):
        value = payload.get(key)
        if not isinstance(value, str) or not value or len(value) > maxlen:
            raise WorkflowError('payload inválido para ' + kind + where)

    def need_sha(key):
        value = payload.get(key)
        if not isinstance(value, str) or not SHA256_RE.match(value):
            raise WorkflowError('payload inválido para ' + kind + where)

    def need_int(key, minimum=None):
        value = payload.get(key)
        if not _is_int(value) or (minimum is not None and value < minimum):
            raise WorkflowError('payload inválido para ' + kind + where)

    def need_observation():
        value = payload.get('observation')
        if not isinstance(value, str) or not OBSERVATION_RE.match(value):
            raise WorkflowError('payload inválido para ' + kind + where)

    if kind == 'PLAN_LOADED':
        exact('plan_sha256', 'name', 'workspace', 'run_id', 'steps', 'run_root')
        need_sha('plan_sha256')
        need_text('name', 128)
        need_text('workspace', 4096)
        need_text('run_id', 64)
        need_int('steps', 0)
        need_text('run_root', 4096)
    elif kind == 'PHASE_STARTED':
        exact('step_id', 'name', 'max_rounds')
        need_text('step_id', 64)
        need_text('name', 128)
        max_rounds = payload['max_rounds']
        if max_rounds is not None and (not _is_int(max_rounds) or max_rounds < 1):
            raise WorkflowError('payload inválido para ' + kind + where)
    elif kind == 'STEP_STARTED':
        exact('step_id', 'step_type', 'attempt')
        need_text('step_id', 64)
        if payload['step_type'] not in STEP_TYPES:
            raise WorkflowError('payload inválido para ' + kind + where)
        need_int('attempt', 1)
    elif kind == 'STEP_COMPLETED':
        base = {'step_id', 'attempt', 'observation', 'output_sha256', 'deps'}
        optional = {'prompt_sha256', 'result_sha256', 'result_path'}
        keys = set(payload)
        if not base <= keys or keys - (base | optional):
            raise WorkflowError('payload inválido para ' + kind + where)
        need_text('step_id', 64)
        need_int('attempt', 1)
        need_observation()
        need_sha('output_sha256')
        if 'prompt_sha256' in payload:
            need_sha('prompt_sha256')
        if 'result_sha256' in payload:
            need_sha('result_sha256')
        if 'result_path' in payload:
            value = payload['result_path']
            if (not isinstance(value, str) or not value or Path(value).is_absolute()
                    or '..' in Path(value).parts or len(value) > 1024):
                raise WorkflowError('payload inválido para ' + kind + where)
        deps = payload['deps']
        if not isinstance(deps, dict):
            raise WorkflowError('payload inválido para ' + kind + where)
        for dep, digest in deps.items():
            if (not isinstance(dep, str) or not STEP_ID_RE.match(dep)
                    or not isinstance(digest, str) or not SHA256_RE.match(digest)):
                raise WorkflowError('payload inválido para ' + kind + where)
    elif kind == 'GATE_REJECTED':
        exact('step_id', 'attempt', 'exit_code', 'output_sha256', 'observation')
        need_text('step_id', 64)
        need_int('attempt', 1)
        need_int('exit_code')
        need_sha('output_sha256')
        need_observation()
    elif kind == 'STEP_FAILED':
        exact('step_id', 'attempt', 'exit_code', 'action', 'observation')
        need_text('step_id', 64)
        need_int('attempt', 1)
        need_int('exit_code')
        if payload['action'] not in ('abort', 'continue'):
            raise WorkflowError('payload inválido para ' + kind + where)
        need_observation()
    elif kind == 'ROUND_CAP_REACHED':
        exact('step_id', 'rounds')
        need_text('step_id', 64)
        need_int('rounds', 1)
    elif kind == 'RUN_RETAINED':
        exact('cause')
        need_text('cause', 256)
    elif kind == 'RUN_COMPLETED':
        exact()
    else:  # kind ya validado contra KINDS por el llamante
        raise WorkflowError('kind de evento desconocido' + where)


def _read_verified(run_dir, limit):
    """Replay completo del journal; falla cerrada ante alteración, truncado
    o prolongado (patrón metrics.py)."""
    journal = run_dir / JOURNAL_NAME
    if not journal.is_file():
        raise WorkflowError('falta ' + JOURNAL_NAME)
    checkpoint = _checkpoint(run_dir)
    raw = journal.read_bytes()
    if len(raw) > limit:
        raise WorkflowError('almacén demasiado grande')
    if raw and not raw.endswith(b'\n'):
        raise WorkflowError(JOURNAL_NAME + ' termina sin salto de línea')
    payloads = []
    prev = GENESIS
    for seq, line in enumerate(raw.split(b'\n')[:-1]):
        where = ' (línea ' + str(seq) + ')'
        if len(line) > MAX_RECORD:
            raise WorkflowError('registro demasiado grande' + where)
        try:
            envelope = json.loads(line)
        except ValueError as error:
            raise WorkflowError('registro ilegible' + where) from error
        if (not isinstance(envelope, dict) or isinstance(envelope.get('version'), bool)
                or envelope.get('version') != 1 or set(envelope) != ENVELOPE_KEYS):
            raise WorkflowError('registro inválido' + where)
        content = {name: envelope[name] for name in CONTENT_KEYS}
        if envelope['content_sha256'] != _sha256_bytes(_canonical(content)):
            raise WorkflowError('registro alterado' + where)
        if content['seq'] != seq or content['prev_sha256'] != prev:
            raise WorkflowError('cadena del journal rota' + where)
        if content['kind'] not in KINDS:
            raise WorkflowError('kind de evento desconocido' + where)
        _validate_payload(content['kind'], content['payload'], where)
        prev = envelope['content_sha256']
        payloads.append(envelope)
    if len(payloads) != checkpoint['events'] or prev != checkpoint['head']:
        raise WorkflowError('Digest global no coincide: journal alterado, truncado o prolongado')
    return payloads


def read_journal(run_dir, *, journal_limit=None):
    """Devuelve los registros verificados del journal (replay completo)."""
    limit = MAX_STORE if journal_limit is None else _journal_limit(journal_limit)
    return _read_verified(Path(run_dir), limit)


def verify(run_dir, *, journal_limit=None):
    """Replay completo: exit de la cadena, del punto de control y de la
    instantánea del plan; falla cerrada."""
    run_dir = Path(run_dir)
    limit = MAX_STORE if journal_limit is None else _journal_limit(journal_limit)
    payloads = _read_verified(run_dir, limit)
    if not payloads or payloads[0]['kind'] != 'PLAN_LOADED':
        raise WorkflowError('journal sin PLAN_LOADED inicial')
    snapshot = run_dir / SNAPSHOT_NAME
    if not snapshot.is_file():
        raise WorkflowError('falta ' + SNAPSHOT_NAME)
    raw = snapshot.read_bytes()
    if len(raw) > MAX_PLAN_BYTES:
        raise WorkflowError('instantánea del plan demasiado grande')
    if _sha256_bytes(raw) != payloads[0]['payload']['plan_sha256']:
        raise WorkflowError(SNAPSHOT_NAME + ' no coincide con PLAN_LOADED')
    return {'events': len(payloads), 'head_sha256': payloads[-1]['content_sha256'],
            'run_dir': str(run_dir)}


def _journal_limit(value):
    if not _is_int(value) or value < 1:
        raise WorkflowError('tope de almacén inválido')
    return value


def _write_head(run_dir, events, head_sha256):
    raw = _canonical({'kind': HEAD_KIND, 'version': 1, 'events': events,
                      'head_sha256': head_sha256}) + b'\n'
    with tempfile.NamedTemporaryFile(dir=run_dir, prefix='.head-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, run_dir / HEAD_NAME)
        finally:
            temporary.unlink(missing_ok=True)


class _JournalWriter:
    """Append-only con digest encadenado; creación exclusiva y head atómico."""

    def __init__(self, run_dir, limit, seq, prev, events):
        self.run_dir = run_dir
        self.limit = limit
        self.seq = seq
        self.prev = prev
        self.events = events
        self.path = run_dir / JOURNAL_NAME

    def append(self, kind, payload, *, terminal=False):
        envelope = {'version': 1, 'seq': self.seq, 'event_id': 'e-' + secrets.token_urlsafe(12),
                    'kind': kind, 'payload': payload, 'prev_sha256': self.prev}
        content_sha256 = _sha256_bytes(_canonical(envelope))
        envelope['content_sha256'] = content_sha256
        line = _canonical(envelope) + b'\n'
        if len(line) > MAX_RECORD:
            raise _RecordTooLarge('registro excede ' + str(MAX_RECORD) + ' B')
        current = self.path.stat().st_size if self.path.exists() else 0
        reserve = 0 if terminal else RETAINED_RESERVE
        if current + len(line) + reserve > self.limit:
            raise _StoreFull('almacén alcanzaría su tope')
        if self.events == 0:
            try:
                stream = self.path.open('xb')  # Creación exclusiva del almacén.
            except FileExistsError as error:
                raise WorkflowError('journal creado por otro escritor') from error
        else:
            stream = self.path.open('ab')
        with stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        self.seq += 1
        self.events += 1
        self.prev = content_sha256
        _write_head(self.run_dir, self.events, content_sha256)
        return envelope


# ------------------------------------------------- ask: preset y folding

def _rpc_items(value):
    """Desenvuelve la respuesta de un listado DSH (patrón transaction)."""
    value = value.get('value', value) if isinstance(value, dict) else value
    if isinstance(value, dict):
        return value.get('items', value.get('presets', []))
    return value if isinstance(value, list) else []


# Misma forma id/name que publica el bundle; patrón de la cara 'actual' de
# transaction.py:_active_presets_match.
_PLUGIN_ROW_RE = re.compile(
    r"(?m)^\s*-\s+id:\s*['\"]?([^'\"\s]+)['\"]?\s*$"
    r"\n\s+name:\s*['\"]?([^'\"\s]+)['\"]?\s*$")
_GUARD_BASENAME = 'anti-escalation.mjs'
_DSH_PLUGIN_NAMES = REQUIRED_MODE_PLUGINS - {ANTI_ESCALATION_PLUGIN}


def _composition_detail(content):
    """Composición operativa exacta del preset, incl. ./anti-escalation.mjs.

    La publicación resuelve la ruta del guardián al bundle (ver
    transaction.py:_active_presets_match), así que se acepta './anti-escalation.mjs'
    o cualquier nombre cuyo basename sea anti-escalation.mjs; los demás plugins
    operativos deben aparecer exactamente una vez y no puede haber otros.
    """
    rows = _PLUGIN_ROW_RE.findall(content)
    ids = [row_id for row_id, _name in rows]
    names = [name for _row_id, name in rows]
    if len(rows) != len(_DSH_PLUGIN_NAMES) + 1:
        return 'la composición debe tener exactamente %d plugins y tiene %d filas' % (
            len(_DSH_PLUGIN_NAMES) + 1, len(rows))
    if len(set(ids)) != len(ids):
        return 'ids de plugin duplicados'
    missing = sorted(name for name in _DSH_PLUGIN_NAMES if names.count(name) != 1)
    if missing:
        return 'plugins operativos ausentes o repetidos: ' + ', '.join(missing)
    guards = [name for name in names
              if name == ANTI_ESCALATION_PLUGIN
              or os.path.basename(name) == _GUARD_BASENAME]
    if len(guards) != 1:
        return 'guardián anti-escalación ausente o repetido'
    return None


def _verify_preset(client, preset_id):
    """agentPresets/list + agentPresets/read con composición exacta.

    Devuelve None si el preset está sano y verificado; en otro caso un
    detalle nombrando la pieza que falta. Los errores de transporte se
    convierten en detalle (la abstención preflight es retratable y no
    envenena reintentos)."""
    try:
        roster = _rpc_items(client.list_agent_presets())
        item = next((row for row in roster
                     if isinstance(row, dict) and row.get('id') == preset_id), None)
        if item is None:
            return 'preset ausente en agentPresets/list: ' + str(preset_id)
        if item.get('broken') is True:
            return 'preset roto en agentPresets/list: ' + str(preset_id)
        document = client.read_agent_preset(preset_id)
        document = document.get('value', document) if isinstance(document, dict) else document
        if not isinstance(document, dict) or document.get('agentPreset') != preset_id:
            return 'agentPresets/read no confirmó el preset: ' + str(preset_id)
        content = document.get('content')
        if not isinstance(content, str) or not content.strip():
            return 'agentPresets/read sin contenido: ' + str(preset_id)
    except (ValueError, OSError, urllib.error.URLError) as error:
        return 'verificación de preset falló: ' + str(error)
    detail = _composition_detail(content)
    return None if detail is None else detail + ': ' + str(preset_id)


def _brief(error):
    return str(error)[:160]


def _assistant_text(data):
    """Extrae el texto de un mensaje de asistente; None si no es extraíble."""
    message = data.get('message', data)
    if isinstance(message, str):
        return message if message.strip() else None
    if isinstance(message, dict):
        text = message.get('text')
        if isinstance(text, str) and text.strip():
            return text
    text = data.get('text')
    if isinstance(text, str) and text.strip():
        return text
    return None


def _new_ask_state():
    return {'cursor': -1, 'open_turn': None, 'request_turn': None,
            'terminal': False, 'texts': []}


def _fold_ask(observation, state, request_id):
    """Folding del turno correlacionado con quiescencia transitiva fail-closed.

    Patrón de acceptance_reviewer (turn/start; user/message con rpcId del
    request fija el turno; turn/end de ese turno es terminal; hijos/jobs
    malformados cuentan como activos y bloquean) extendido con la extracción
    del texto del asistente del turno correlacionado, que el folding original
    no consumía. Falla cerrada ante datos que impiden correlacionar.
    """
    if not isinstance(observation, dict) or not isinstance(observation.get('running'), bool):
        raise ValueError('observación DSH sin running booleano')
    events = observation.get('events')
    descendants = observation.get('descendants', observation.get('children', []))
    jobs = observation.get('jobs', [])
    if not all(isinstance(items, list) for items in (events, descendants, jobs)):
        raise ValueError('observación DSH con eventos/hijos/jobs que no son listas')
    cursor = state['cursor']
    open_turn = state['open_turn']
    request_turn = state['request_turn']
    terminal = state['terminal']
    for event in events:
        if not isinstance(event, dict):
            continue
        seq = event.get('seq')
        if isinstance(seq, int):
            cursor = max(cursor, seq)
        data = event.get('data')
        if not isinstance(data, dict):
            continue
        event_type = event.get('type')
        if event_type == 'turn/start':
            open_turn = data.get('turn')
        elif event_type == 'user/message':
            message = data.get('message', data)
            source = message.get('source') if isinstance(message, dict) else None
            if isinstance(source, dict) and source.get('rpcId') == request_id:
                event_turn = data.get('turn')
                request_turn = event_turn if isinstance(event_turn, int) else open_turn
                if not isinstance(request_turn, int):
                    raise ValueError('user/message del request sin turno correlacionable')
        elif event_type == 'assistant/message':
            if request_turn is None or data.get('turn') != request_turn:
                continue
            text = _assistant_text(data)
            if text is None:
                raise ValueError('assistant/message del turno correlacionado sin texto extraíble')
            state['texts'].append(text)
        elif (event_type == 'turn/end' and request_turn is not None
                and data.get('turn') == request_turn):
            terminal = True
    observed = observation.get('cursor')
    if isinstance(observed, int):
        cursor = max(cursor, observed)
    child_running = any(not isinstance(child, dict) or child.get('running') is not False
                        for child in descendants)
    active_jobs = any(not isinstance(job, dict)
                      or job.get('status') in (None, 'running', 'stopping')
                      for job in jobs)
    state.update({'cursor': cursor, 'open_turn': open_turn, 'request_turn': request_turn,
                  'terminal': terminal,
                  'quiescent': (not observation['running'] and not child_running
                                and not active_jobs)})
    return state


def _ask_quiescent(client, session_id, state):
    """Observa la sesión y devuelve (quiescente, estado) sin correlación;
    cualquier dato malformado cuenta como no quiescente."""
    try:
        observation = client.creator_observation(session_id, cursor=state['cursor'])
    except (ValueError, OSError, urllib.error.URLError):
        return False, state
    running = observation.get('running') if isinstance(observation, dict) else None
    descendants = observation.get('descendants', observation.get('children', [])) if isinstance(observation, dict) else None
    jobs = observation.get('jobs') if isinstance(observation, dict) else None
    if not isinstance(running, bool) or not isinstance(descendants, list) or not isinstance(jobs, list):
        return False, state
    cursor = observation.get('cursor')
    if isinstance(cursor, int):
        state['cursor'] = max(state['cursor'], cursor)
    child_running = any(not isinstance(child, dict) or child.get('running') is not False
                        for child in descendants)
    active_jobs = any(not isinstance(job, dict)
                      or job.get('status') in (None, 'running', 'stopping')
                      for job in jobs)
    return (not running and not child_running and not active_jobs), state


# ------------------------------------------------------------ replay

def _empty_state():
    return {'completed': {}, 'attempts': {}, 'phase': None,
            'phase_started_ids': set(), 'plan_sha256': None, 'pending_asks': {}}


def _latest_ask_dispatch(run_dir, step_id, attempt):
    """Estado de despacho del intento pendiente, del fichero de observación.

    'dispatched' -> sesión viva reutilizable ([corr-3]); 'unknown' -> el
    intento no llegó a registrar sesión (fail-closed: se retiene); 'failed'
    -> el intento murió sin sesión (se permite uno nuevo); 'ilegible' ->
    estado corrupto (se retiene)."""
    observations = run_dir / OBSERVATIONS_NAME
    pattern = re.compile(r'^([0-9]+)-' + re.escape(step_id) + r'-ask\.json$')
    best = None
    if observations.is_dir():
        for entry in observations.iterdir():
            match = pattern.match(entry.name)
            if not match:
                continue
            try:
                body = json.loads(entry.read_bytes().decode('utf-8'))
            except (ValueError, UnicodeDecodeError, OSError):
                body = None
            if not isinstance(body, dict) or body.get('attempt') != attempt:
                continue
            number = int(match.group(1))
            if best is None or number > best[0]:
                best = (number, body)
    if best is None:
        return {'status': 'unknown', 'attempt': attempt, 'session_id': None,
                'request_id': None}
    body = best[1]
    session_id = body.get('session_id')
    request_id = body.get('request_id')
    if (not isinstance(session_id, str) or not session_id
            or not isinstance(request_id, str) or not request_id
            or body.get('status') not in ('dispatched', 'failed')):
        return {'status': 'ilegible', 'attempt': attempt, 'session_id': None,
                'request_id': None}
    if body['status'] == 'failed':
        return None  # Intento muerto sin sesión: se permite uno nuevo.
    return {'status': 'dispatched', 'attempt': attempt, 'session_id': session_id,
            'request_id': request_id}


def _replay(payloads, run_dir):
    """Estado derivado del journal verificado; solo se consideran completados
    los pasos con STEP_COMPLETED cuya observación verifica su sha256."""
    state = _empty_state()
    started_types = {}
    started_counts = {}
    completed_counts = {}
    for envelope in payloads:
        kind = envelope['kind']
        payload = envelope['payload']
        if kind == 'PLAN_LOADED':
            state['plan_sha256'] = payload['plan_sha256']
        elif kind == 'PHASE_STARTED':
            state['phase_started_ids'].add(payload['step_id'])
            state['phase'] = {'name': payload['name'], 'max_rounds': payload['max_rounds'],
                              'count': 0}
        elif kind == 'STEP_STARTED':
            step_id = payload['step_id']
            state['attempts'][step_id] = max(state['attempts'].get(step_id, 0), payload['attempt'])
            started_types[step_id] = payload['step_type']
            started_counts[step_id] = started_counts.get(step_id, 0) + 1
        elif kind == 'STEP_COMPLETED':
            state['completed'][payload['step_id']] = dict(payload)
            completed_counts[payload['step_id']] = completed_counts.get(payload['step_id'], 0) + 1
        elif kind == 'GATE_REJECTED':
            if state['phase'] is not None:
                state['phase']['count'] += 1
    verified = {}
    for step_id, item in state['completed'].items():
        path = run_dir / item['observation']
        if path.is_file() and _sha256_bytes(path.read_bytes()) == item['output_sha256']:
            verified[step_id] = item
    # Un join completado exige que cada dep siga verificado con su digest.
    for step_id, item in list(verified.items()):
        for dep, digest in item['deps'].items():
            other = verified.get(dep)
            if other is None or other['output_sha256'] != digest:
                verified.pop(step_id)
                break
    state['completed'] = verified
    pending_asks = {}
    for step_id, step_type in started_types.items():
        if step_type != 'ask' or completed_counts.get(step_id, 0) >= started_counts.get(step_id, 0):
            continue
        # Un ask re-ejecutado (sin STEP_COMPLETED verificado) tras haber
        # completado antes no deja intento pendiente nuevo: el despacho
        # corresponde al intento máximo iniciado.
        pending_asks[step_id] = _latest_ask_dispatch(run_dir, step_id,
                                                     state['attempts'][step_id])
    state['pending_asks'] = {step_id: pending for step_id, pending in pending_asks.items()
                             if pending is not None}
    return state


# ----------------------------------------------------------- ejecutor

class _Run:
    def __init__(self, plan, run_dir, writer, state, *, ask_client=None, run_id=None):
        self.plan = plan
        self.workspace = plan['workspace']
        self.run_dir = run_dir
        self.writer = writer
        self.completed = state['completed']
        self.attempts = state['attempts']
        self.phase = state['phase']
        self.phase_started_ids = state['phase_started_ids']
        self.pending_asks = state['pending_asks']
        self.ask_client = ask_client
        self.run_id = run_id or ''
        self.last_ask_observation = None  # Resultado del ask previo para WORKFLOW_OBSERVATION.
        self.retained_journaled = None
        observations = run_dir / OBSERVATIONS_NAME
        top = 0
        if observations.is_dir():
            for entry in observations.iterdir():
                match = OBS_NUMBER_RE.match(entry.name)
                if match:
                    top = max(top, int(match.group(1)))
        self._observation_number = top

    # -- registro con retención fail-closed (nunca truncar)
    def record(self, kind, payload, *, terminal=False):
        try:
            return self.writer.append(kind, payload, terminal=terminal)
        except _StoreFull:
            if terminal:
                raise
            self._retain('journal-store-limit')
        except _RecordTooLarge:
            self._retain('journal-record-limit:' + str(payload.get('step_id', '')))

    def _retain(self, cause):
        self.retained_journaled = False
        try:
            self.writer.append('RUN_RETAINED', {'cause': cause}, terminal=True)
            self.retained_journaled = True
        except (_StoreFull, _RecordTooLarge, OSError):
            pass
        raise _Retained(cause)

    # -- observaciones
    def _write_observation(self, step_id, intent, attempt, **content):
        self._observation_number += 1
        relative = ('%s/%02d-%s-%s.json' % (OBSERVATIONS_NAME, self._observation_number,
                                            step_id, intent))
        body = {'step': step_id, 'intent': intent, 'attempt': attempt}
        body.update(content)
        data = _canonical(body) + b'\n'
        path = self.run_dir / relative
        try:
            stream = path.open('xb')
        except FileExistsError as error:
            raise WorkflowError('observación ya existente: ' + relative) from error
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return relative, data

    # -- pasos
    def execute(self, step):
        if step['id'] in self.completed:
            return  # Reanudación: solo se salta con STEP_COMPLETED verificado.
        if step['type'] == 'gate':
            self._gate(step)
        elif step['type'] == 'join':
            self._join(step)
        elif step['type'] == 'fase':
            self._fase(step)
        else:
            self._ask(step)

    def _fase(self, step):
        if step['id'] in self.phase_started_ids:
            return  # Ya iniciada en una ejecución previa: el conteo continúa.
        self.record('PHASE_STARTED', {'step_id': step['id'], 'name': step['name'],
                                      'max_rounds': step['max_rounds']})
        self.phase_started_ids.add(step['id'])
        self.phase = {'name': step['name'], 'max_rounds': step['max_rounds'], 'count': 0}

    def _gate(self, step):
        step_id = step['id']
        action = step['on_fail']['action']
        rounds = step['on_fail']['rounds']
        failures = 0
        while True:
            attempt = self.attempts.get(step_id, 0) + 1
            self.attempts[step_id] = attempt
            self.record('STEP_STARTED', {'step_id': step_id, 'step_type': 'gate',
                                         'attempt': attempt})
            env = dict(os.environ)
            if self.last_ask_observation is not None:
                env['WORKFLOW_OBSERVATION'] = str(self.last_ask_observation)
            exit_code = None
            error = None
            stdout = ''
            stderr = ''
            try:
                proc = subprocess.run(step['command'], cwd=str(self.workspace), env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                exit_code = proc.returncode
                stdout = proc.stdout[:MAX_CAPTURE_BYTES].decode('utf-8', 'replace')
                stderr = proc.stderr[:MAX_CAPTURE_BYTES].decode('utf-8', 'replace')
            except OSError as exc:
                error = type(exc).__name__ + ': ' + str(exc)
            relative, data = self._write_observation(step_id, 'gate', attempt,
                                                     exit_code=exit_code, stdout=stdout,
                                                     stderr=stderr, error=error)
            output_sha256 = _sha256_bytes(data)
            if error is not None:
                self._retain('gate-impossible:' + step_id + ':spawn')
            if exit_code == 0:
                self.record('STEP_COMPLETED', {'step_id': step_id, 'attempt': attempt,
                                               'observation': relative,
                                               'output_sha256': output_sha256, 'deps': {}})
                self.completed[step_id] = {'step_id': step_id, 'attempt': attempt,
                                           'observation': relative,
                                           'output_sha256': output_sha256, 'deps': {}}
                return
            if exit_code == 1:
                self.record('GATE_REJECTED', {'step_id': step_id, 'attempt': attempt,
                                              'exit_code': 1, 'output_sha256': output_sha256,
                                              'observation': relative})
                if self.phase is not None:
                    self.phase['count'] += 1
                    if (self.phase['max_rounds'] is not None
                            and self.phase['count'] > self.phase['max_rounds']):
                        self._retain('fase-rounds-exceeded:' + self.phase['name'])
                failures += 1
                if action == 'retry':
                    if failures >= rounds:
                        self.record('ROUND_CAP_REACHED', {'step_id': step_id, 'rounds': rounds})
                        self._retain('gate-rounds-exhausted:' + step_id)
                    continue
                self.record('STEP_FAILED', {'step_id': step_id, 'attempt': attempt,
                                            'exit_code': 1, 'action': action,
                                            'observation': relative})
                if action == 'abort':
                    self._retain('gate-abort:' + step_id)
                return  # continue: el paso queda fallido y la ejecución sigue
            self._retain('gate-impossible:' + step_id + ':exit=' + str(exit_code))

    def _join(self, step):
        step_id = step['id']
        attempt = self.attempts.get(step_id, 0) + 1
        self.attempts[step_id] = attempt
        self.record('STEP_STARTED', {'step_id': step_id, 'step_type': 'join', 'attempt': attempt})
        digests = {}
        for dep in step['depends']:
            done = self.completed.get(dep)
            if done is None:
                self._retain('join-dep-not-completed:' + step_id + ':' + dep)
            digests[dep] = done['output_sha256']
        relative, data = self._write_observation(step_id, 'join', attempt, deps=digests)
        payload = {'step_id': step_id, 'attempt': attempt, 'observation': relative,
                   'output_sha256': _sha256_bytes(data), 'deps': digests}
        self.record('STEP_COMPLETED', payload)
        self.completed[step_id] = dict(payload)

    # -- ask (U3)

    def _request_id(self, step_id, attempt):
        """Identidad determinista del intento: sha256(run_id, step_id, attempt)."""
        return hashlib.sha256(
            ('%s|%s|%d' % (self.run_id, step_id, attempt)).encode('utf-8')).hexdigest()

    def _write_ask_state(self, step_id, attempt, session_id, request_id,
                         prompt_sha256, status, **extra):
        body = {'session_id': session_id, 'request_id': request_id,
                'prompt_sha256': prompt_sha256, 'status': status}
        body.update(extra)
        return self._write_observation(step_id, 'ask', attempt, **body)

    def _ask(self, step):
        step_id = step['id']
        pending = self.pending_asks.get(step_id)
        if pending is not None:
            self._ask_resume(step, pending)
            return
        attempt = self.attempts.get(step_id, 0) + 1
        self.attempts[step_id] = attempt
        self.record('STEP_STARTED', {'step_id': step_id, 'step_type': 'ask',
                                     'attempt': attempt})
        request_id = self._request_id(step_id, attempt)
        prompt_sha256 = _sha256_bytes(step['prompt'].encode('utf-8'))
        # Sesión NUEVA por intento con el preset verificado del proyecto;
        # nunca se adoptan sesiones ajenas.
        try:
            session_id = self.ask_client.create_creator_session(
                workspace_path=str(self.workspace), agent_preset=self.plan['preset'])
        except (ValueError, OSError, urllib.error.URLError) as error:
            self._write_ask_state(step_id, attempt, None, request_id,
                                  prompt_sha256, 'failed', error=_brief(error))
            self._retain('ask-sesion-no-creada:' + step_id + ':' + _brief(error))
        self._write_ask_state(step_id, attempt, session_id, request_id,
                              prompt_sha256, 'dispatched')
        try:
            self.ask_client.send_prompt(session_id, step['prompt'], request_id=request_id)
        except (ValueError, OSError, urllib.error.URLError) as error:
            self._close_ask(session_id)
            self._retain('ask-despacho-fallo:' + step_id + ':' + _brief(error))
        self._poll_ask(step, attempt, session_id, request_id, prompt_sha256)

    def _ask_resume(self, step, pending):
        """[corr-3]: intento sin terminal. Sesión viva -> re-envío del MISMO
        request_id a la MISMA sesión o re-observación del transcript; sesión
        perdida -> RUN_RETAINED, nunca re-despacho a sesión nueva."""
        step_id = step['id']
        attempt = pending['attempt']
        if pending['status'] == 'unknown':
            self._retain('ask-sesion-desconocida:' + step_id)
        if pending['status'] == 'ilegible':
            self._retain('ask-estado-ilegible:' + step_id)
        request_id = self._request_id(step_id, attempt)
        if pending['request_id'] != request_id:
            self._retain('ask-estado-ilegible:' + step_id + ':request_id no determinista')
        session_id = pending['session_id']
        prompt_sha256 = _sha256_bytes(step['prompt'].encode('utf-8'))
        state = _new_ask_state()
        try:
            observation = self.ask_client.creator_observation(session_id, cursor=-1)
            state = _fold_ask(observation, state, request_id)
        except (ValueError, OSError, urllib.error.URLError) as error:
            self._retain('ask-sesion-perdida:' + step_id + ':' + _brief(error))
        if state['request_turn'] is None:
            # El transcript no muestra este request: re-envío del mismo id.
            try:
                self.ask_client.send_prompt(session_id, step['prompt'],
                                            request_id=request_id)
            except (ValueError, OSError, urllib.error.URLError) as error:
                self._close_ask(session_id)
                self._retain('ask-despacho-fallo:' + step_id + ':' + _brief(error))
        self._poll_ask(step, attempt, session_id, request_id, prompt_sha256, state)

    def _poll_ask(self, step, attempt, session_id, request_id, prompt_sha256,
                  state=None):
        step_id = step['id']
        if state is None:
            state = _new_ask_state()
        deadline = time.monotonic() + step['timeout_s']
        while True:
            if time.monotonic() >= deadline:
                confirmed = self._close_ask(session_id, state)
                if confirmed:
                    self._retain('ask-deadline:' + step_id + ':cancelada y quiescente')
                self._retain('ask-deadline:' + step_id + ':sin quiescencia confirmada')
            try:
                observation = self.ask_client.creator_observation(
                    session_id, cursor=state['cursor'])
                state = _fold_ask(observation, state, request_id)
            except (ValueError, OSError, urllib.error.URLError) as error:
                # Trampa de red: nunca una excepción sin retención; antes de
                # retener se intenta no abandonar la sesión sin cierre.
                self._close_ask(session_id, state)
                self._retain('ask-observacion-fallo:' + step_id + ':' + _brief(error))
            if state['terminal'] and state['quiescent']:
                break
            time.sleep(ASK_POLL_SECONDS)
        text = '\n\n'.join(state['texts']) if state['texts'] else None
        if text is None:
            self._retain('ask-sin-texto:' + step_id + ':' + session_id)
        result_path = None
        result_payload = None
        result_sha256 = None
        if step['result_contract'] is not None:
            result_path, result_payload, result_sha256 = self._load_result(
                step_id, step['result_contract']['path'])
        relative, data = self._write_ask_state(
            step_id, attempt, session_id, request_id, prompt_sha256, 'completed',
            text=text, result=result_payload, result_path=result_path)
        payload = {'step_id': step_id, 'attempt': attempt, 'observation': relative,
                   'output_sha256': _sha256_bytes(data), 'deps': {},
                   'prompt_sha256': prompt_sha256}
        if result_sha256 is not None:
            payload['result_sha256'] = result_sha256
            payload['result_path'] = result_path
        self.record('STEP_COMPLETED', payload)
        self.completed[step_id] = dict(payload)
        contract = step['result_contract']
        # WORKFLOW_OBSERVATION: la ruta del resultado del ask previo.
        self.last_ask_observation = ((self.workspace / 'evidence' / contract['path'])
                                     if contract is not None
                                     else self.run_dir / relative)

    def _load_result(self, step_id, relative):
        """Valida el resultado estructurado en <workspace>/evidence ([corr-4])."""
        evidence = (self.workspace / 'evidence').resolve()
        target = (evidence / relative).resolve()
        if target == evidence or evidence not in target.parents or not target.is_file():
            self._retain('ask-sin-resultado:' + step_id + ':' + relative)
        data = target.read_bytes()
        if len(data) > MAX_RESULT_BYTES:
            self._retain('ask-resultado-demasiado-grande:' + step_id)
        try:
            value = json.loads(data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as error:
            self._retain('ask-resultado-ilegible:' + step_id + ':' + _brief(error))
        if not isinstance(value, dict):
            self._retain('ask-resultado-ilegible:' + step_id + ':no es un objeto JSON')
        return (target.relative_to(self.workspace.resolve()).as_posix(),
                value, _sha256_bytes(data))

    def _close_ask(self, session_id, state=None):
        """cancel_session + gracia de 30 s; True solo con quiescencia confirmada.

        Nunca lanza: un fallo de cancelación cuenta como no confirmado."""
        if state is None:
            state = {'cursor': -1}
        try:
            self.ask_client.cancel_session(session_id)
        except (ValueError, OSError, urllib.error.URLError):
            return False
        deadline = time.monotonic() + ASK_CANCEL_GRACE_SECONDS
        while time.monotonic() < deadline:
            quiescent, state = _ask_quiescent(self.ask_client, session_id, state)
            if quiescent:
                return True
            time.sleep(ASK_POLL_SECONDS)
        return False


def run_plan(plan_path, *, journal_limit=None, ask_client=None, run_root=None):
    """Ejecuta un plan; devuelve el resultado (COMPLETED/RETAINED/ABSTAINED).

    Falla con WorkflowError ante plan inválido o journal corrupto, sin
    escribir nada en esos casos. Con ask y sin cliente DSH, o con ask sin
    preset verificado, se abstiene sin crear run dir. run_root es la
    anulación de la CLI sobre el run_root del plan; por defecto manda el
    hermano externo <workspace>-workflow.
    """
    plan, raw = load_plan(plan_path)
    plan_sha256 = _sha256_bytes(raw)
    has_ask = any(step['type'] == 'ask' for step in plan['steps'])
    if has_ask and ask_client is None:
        return {'result': 'ABSTAINED',
                'reason': 'plan con paso ask sin cliente DSH disponible'}
    if has_ask:
        # Preflight de abstención antes de tocar disco: sin preset declarado
        # o sin preset verificado no hay run dir ni journal.
        if plan['preset'] is None:
            return {'result': 'ABSTAINED',
                    'reason': 'plan con paso ask sin preset verificado: '
                              'el plan no declara preset'}
        detail = _verify_preset(ask_client, plan['preset'])
        if detail is not None:
            return {'result': 'ABSTAINED',
                    'reason': 'plan con paso ask sin preset verificado: ' + detail}
    limit = MAX_STORE if journal_limit is None else _journal_limit(journal_limit)
    if run_root is not None:
        resolved_root = _resolve_run_root(plan['workspace'], run_root)
    else:
        resolved_root = (plan['run_root'] if plan['run_root'] is not None
                         else _default_run_root(plan['workspace']))
    run_dir = resolved_root / _run_id_for(plan_sha256)
    journal_path = run_dir / JOURNAL_NAME
    if journal_path.is_file():
        payloads = _read_verified(run_dir, limit)
        if not payloads or payloads[0]['kind'] != 'PLAN_LOADED':
            raise WorkflowError('journal sin PLAN_LOADED inicial')
        snapshot = run_dir / SNAPSHOT_NAME
        if not snapshot.is_file():
            raise WorkflowError('run dir existente sin ' + SNAPSHOT_NAME)
        if _sha256_bytes(snapshot.read_bytes()) != plan_sha256:
            raise WorkflowError('el plan difiere de la instantánea del run dir')
        state = _replay(payloads, run_dir)
        writer = _JournalWriter(run_dir, limit, len(payloads),
                                payloads[-1]['content_sha256'], len(payloads))
    else:
        state = _empty_state()
        writer = _JournalWriter(run_dir, limit, 0, GENESIS, 0)
        try:
            if not run_dir.is_dir():
                resolved_root.mkdir(mode=0o700, parents=True, exist_ok=True)
                run_dir.mkdir(mode=0o700)
            (run_dir / OBSERVATIONS_NAME).mkdir(mode=0o700, exist_ok=True)
            with (run_dir / SNAPSHOT_NAME).open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise WorkflowError('run dir ya preparado sin journal: inspección requerida') from error
        except OSError as error:
            raise WorkflowError('no se pudo preparar el run dir: ' + str(error)) from error
        writer.append('PLAN_LOADED', {'plan_sha256': plan_sha256, 'name': plan['name'],
                                      'workspace': str(plan['workspace']),
                                      'run_id': _run_id_for(plan_sha256),
                                      'steps': len(plan['steps']),
                                      'run_root': str(resolved_root)})
    run = _Run(plan, run_dir, writer, state, ask_client=ask_client,
               run_id=_run_id_for(plan_sha256))
    try:
        for step in plan['steps']:
            run.execute(step)
        run.record('RUN_COMPLETED', {})
    except _Retained as stop:
        return {'result': 'RETAINED', 'cause': stop.cause, 'run_dir': str(run_dir),
                'events': writer.events, 'journaled': run.retained_journaled}
    return {'result': 'COMPLETED', 'run_dir': str(run_dir), 'events': writer.events,
            'head_sha256': writer.prev}


def run_plan_entry(plan_path, *, run_root=None):
    """Entrada de bootstrap para `workflow run`.

    Cuando el plan exige ask adquiere el cliente DSH por la vía no-launch
    (reutiliza sesiones existentes; JAMÁS lanza dsh web por sí mismo) y
    deja en run_plan el preflight del preset verificado. Sin cliente
    disponible la ejecución se abstiene nombrando la pieza que falta, sin
    crear run dir ni journal.
    """
    plan, _raw = load_plan(plan_path)
    if not any(step['type'] == 'ask' for step in plan['steps']):
        return run_plan(plan_path, run_root=run_root)
    import creator_client  # Solo con ask: sin ask no se toca ningún home.
    client, reason = creator_client.acquire_dsh_client(launch=False)
    if client is None:
        return {'result': 'ABSTAINED',
                'reason': 'plan con paso ask sin cliente DSH: ' + reason}
    return run_plan(plan_path, run_root=run_root, ask_client=client)


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='workflow.py',
        description='Ejecutor de planes de workflow sin DSH: run ejecuta un plan; '
                    'verify comprueba por replay la cadena del journal de un run dir.')
    sub = parser.add_subparsers(dest='command', required=True)
    p_run = sub.add_parser('run', help='Ejecuta un plan (run dir externo: <workspace>-workflow/<run_id>)')
    p_run.add_argument('plan', help='Ruta del plan JSON')
    p_verify = sub.add_parser('verify', help='Verifica la cadena del journal de un run dir')
    p_verify.add_argument('run_dir', help='Directorio de ejecución')
    args = parser.parse_args(argv)
    if args.command == 'run':
        try:
            outcome = run_plan(args.plan)
        except (WorkflowError, OSError) as error:
            print('workflow: ' + str(error), file=sys.stderr)
            return 2
        if outcome['result'] == 'COMPLETED':
            print(json.dumps({'result': 'COMPLETED', 'run_dir': outcome['run_dir'],
                              'events': outcome['events']}, ensure_ascii=False))
            return 0
        if outcome['result'] == 'ABSTAINED':
            print(json.dumps({'result': 'ABSTAINED', 'reason': outcome['reason']},
                             ensure_ascii=False), file=sys.stderr)
        else:
            print(json.dumps({'result': 'RETAINED', 'cause': outcome['cause']},
                             ensure_ascii=False), file=sys.stderr)
        return 1
    try:
        info = verify(args.run_dir)
    except (WorkflowError, OSError) as error:
        print('workflow: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps({'result': 'VERIFIED', 'events': info['events'],
                      'head_sha256': info['head_sha256'], 'run_dir': info['run_dir']},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
