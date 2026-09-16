#!/usr/bin/env python3
"""Métricas durables por misión; agrega solo desde eventos persistidos.

Almacén append-only (events.jsonl) con creación exclusiva y digest de
contenido por evento, encadenado al anterior; el punto de control head.json
fija el digest global esperado, de modo que un evento alterado, un truncado o
una reapertura con digest global distinto fallan cerrados. Un campo no
observado no se registra (nunca 0 por defecto) y los resúmenes solo suman
eventos persistidos y verificados: las claves sin observaciones se reportan
NO_DISPONIBLE. No concede autoridad ni valida la semántica de las cifras; la
corrección de lo declarado es responsabilidad del caller. Almacén local
confiable de un solo escritor; concurrencia hostil requiere coordinación del
Host.
"""
import hashlib
import json
import math
import os
import secrets
import tempfile

from pathlib import Path

from onboard import checked

KINDS = ('turn', 'repair', 'audit', 'denial', 'retry', 'budget')
METRICS = ('requests', 'tokens_input', 'tokens_cache_read', 'tokens_output',
           'tool_calls', 'denials', 'retries', 'rounds', 'elapsed_s')
NO_DISPONIBLE = 'NO_DISPONIBLE'
MAX_EVENT = 4096
MAX_STORE = 8 * 1024 * 1024
GENESIS = '0' * 64
EVENTS = 'events.jsonl'
HEAD = 'head.json'
CONTENT_KEYS = ('version', 'seq', 'event_id', 'prev_sha256', 'payload')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _quantity(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError('Cantidad inválida: ' + label)
    return value


def _source(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Source requerido: string no vacío')
    return source


def _unit(unit):
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise ValueError('Unit inválida: string no vacío o None')
    return unit


def _root(store):
    root = checked(store)
    if not root.is_dir():
        raise ValueError('Raíz de métricas inválida')
    return root


def _checkpoint(root):
    events, head = root / EVENTS, root / HEAD
    if not events.is_file() or not head.is_file():
        raise ValueError('Almacén incompleto: faltan events.jsonl o head.json')
    raw = head.read_bytes()
    if len(raw) > MAX_EVENT:
        raise ValueError('Punto de control demasiado grande')
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise ValueError('Punto de control ilegible') from error
    if (not isinstance(value, dict) or set(value) != {'kind', 'version', 'events', 'head_sha256'}
            or value.get('kind') != 'metrics-head' or value.get('version') != 1
            or isinstance(value.get('events'), bool) or not isinstance(value.get('events'), int)
            or value['events'] < 0 or not isinstance(value.get('head_sha256'), str)):
        raise ValueError('Punto de control inválido')
    return {'events': value['events'], 'head': value['head_sha256']}


def _write_head(root, checkpoint):
    raw = _canonical(checkpoint) + b'\n'
    with tempfile.NamedTemporaryFile(dir=root, prefix='.head-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, root / HEAD)
        finally:
            temporary.unlink(missing_ok=True)


def _validate_payload(payload, where):
    if not isinstance(payload, dict) or set(payload) != {'kind', 'source', 'unit', 'values'}:
        raise ValueError('Payload de evento inválido' + where)
    if payload['kind'] not in KINDS:
        raise ValueError('Kind de evento inválido' + where)
    _source(payload['source'])
    _unit(payload['unit'])
    values = payload['values']
    if not isinstance(values, dict) or set(values) - set(METRICS):
        raise ValueError('Values de evento inválido' + where)
    for name, value in values.items():
        _quantity(value, name)


def record_event(store, kind, *, source, unit=None, **values):
    """Persiste un evento al cerrar el turno; falla cerrada sin escribir."""
    if kind not in KINDS:
        raise ValueError('Kind de evento desconocido: ' + str(kind))
    _source(source)
    _unit(unit)
    unknown = sorted(set(values) - set(METRICS))
    if unknown:
        raise ValueError('Métricas desconocidas: ' + ', '.join(unknown))
    observed = {name: _quantity(values[name], name) for name in METRICS if name in values}
    root = _root(store)
    if (root / EVENTS).exists() or (root / HEAD).exists():
        state = _checkpoint(root)
    else:
        state = {'events': 0, 'head': GENESIS}
    payload = {'kind': kind, 'source': source, 'unit': unit, 'values': observed}
    envelope = {'version': 1, 'seq': state['events'], 'event_id': 'e-' + secrets.token_urlsafe(12),
                'prev_sha256': state['head'], 'payload': payload}
    envelope['content_sha256'] = hashlib.sha256(_canonical(
        {name: envelope[name] for name in CONTENT_KEYS})).hexdigest()
    line = _canonical(envelope) + b'\n'
    if len(line) > MAX_EVENT:
        raise ValueError('Evento demasiado grande')
    if state['events'] == 0:
        try:
            stream = (root / EVENTS).open('xb')  # Creación exclusiva del almacén.
        except FileExistsError as error:
            raise ValueError('Almacén creado por otro escritor') from error
    else:
        stream = (root / EVENTS).open('ab')
    with stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    _write_head(root, {'kind': 'metrics-head', 'version': 1, 'events': state['events'] + 1,
                       'head_sha256': envelope['content_sha256']})
    return {'event_id': envelope['event_id'], 'seq': state['events'],
            'head_sha256': envelope['content_sha256']}


def _verified(store):
    """Verificación íntegra: digests por evento, cadena y digest global."""
    root = _root(store)
    checkpoint = _checkpoint(root)
    raw = (root / EVENTS).read_bytes()
    if len(raw) > MAX_STORE:
        raise ValueError('Almacén demasiado grande')
    if raw and not raw.endswith(b'\n'):
        raise ValueError('events.jsonl termina sin salto de línea')
    payloads = []
    prev = GENESIS
    for seq, line in enumerate(raw.split(b'\n')[:-1]):
        where = ' (línea ' + str(seq) + ')'
        if len(line) > MAX_EVENT:
            raise ValueError('Evento demasiado grande' + where)
        try:
            envelope = json.loads(line)
        except ValueError as error:
            raise ValueError('Evento ilegible' + where) from error
        if (not isinstance(envelope, dict) or envelope.get('version') != 1
                or set(envelope) != set(CONTENT_KEYS) | {'content_sha256'}):
            raise ValueError('Evento inválido' + where)
        content = {name: envelope[name] for name in CONTENT_KEYS}
        if envelope['content_sha256'] != hashlib.sha256(_canonical(content)).hexdigest():
            raise ValueError('Evento alterado' + where)
        if content['seq'] != seq or content['prev_sha256'] != prev:
            raise ValueError('Cadena de eventos rota' + where)
        _validate_payload(content['payload'], where)
        prev = envelope['content_sha256']
        payloads.append(content['payload'])
    if len(payloads) != checkpoint['events'] or prev != checkpoint['head']:
        raise ValueError('Digest global no coincide: almacén alterado, truncado o prolongado')
    return checkpoint, payloads


def verify(store):
    """Recomputa digests por evento y el digest global; falla cerrada."""
    checkpoint, payloads = _verified(store)
    return {'events': len(payloads), 'head_sha256': checkpoint['head']}


def summarize(store, kinds=None):
    """Agrega solo desde eventos persistidos; lo nunca registrado es NO_DISPONIBLE."""
    if kinds is None:
        wanted = frozenset(KINDS)
    else:
        selected = tuple(kinds)
        if not selected or any(kind not in KINDS for kind in selected):
            raise ValueError('Filtro de kinds inválido')
        wanted = frozenset(selected)
    _, payloads = _verified(store)
    totals = {}
    for payload in payloads:
        if payload['kind'] not in wanted:
            continue
        for name, value in payload['values'].items():
            entry = totals.setdefault(name, {'total': 0, 'count': 0, 'sources': set()})
            entry['total'] += value
            entry['count'] += 1
            entry['sources'].add(payload['source'])
    summary = {}
    for name in METRICS:
        entry = totals.get(name)
        if entry is None:
            summary[name] = NO_DISPONIBLE
        else:
            summary[name] = {'total': entry['total'], 'count': entry['count'],
                             'sources': sorted(entry['sources'])}
    return summary
