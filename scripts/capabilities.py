#!/usr/bin/env python3
"""Validate a Host-issued capability; this module never grants authority."""
import hashlib
import json
from pathlib import Path

from onboard import checked


def _digest(value):
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def _paths(values, label):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
        raise ValueError(f'{label} inválido')
    result = []
    for raw in values:
        path = checked(raw)
        if path != Path(raw) or path in result:
            raise ValueError(f'{label} ambiguo')
        result.append(path)
    return tuple(result)


def load(path):
    path = checked(path)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Capability ausente o excesiva')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Capability v1 inválida')
    for field in ('capability_id', 'session_id', 'project', 'executor'):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f'Falta {field}')
    roots = value.get('roots')
    if not isinstance(roots, dict):
        raise ValueError('Faltan raíces')
    for key in ('product_read', 'framework_execute', 'workspace_write'):
        roots[key] = [str(p) for p in _paths(roots.get(key), key)]
    if not isinstance(value.get('scope', []), list):
        raise ValueError('Scope inválido')
    value['_path'] = path
    return value


def validate(path, *, session_id, project, executor, scope=None, roots=None):
    capability = load(path)
    if any(capability[field] != expected for field, expected in (
            ('session_id', session_id), ('project', project), ('executor', executor))):
        raise ValueError('Capability de otra sesión, proyecto o ejecutor')
    if scope is not None and any(item not in capability['scope'] for item in scope):
        raise ValueError('Scope fuera de capability')
    if roots:
        for key, expected in roots.items():
            actual = tuple(capability['roots'].get(key, ()))
            if tuple(str(checked(item)) for item in expected) != actual:
                raise ValueError(f'Raíz {key} fuera de capability')
    return capability


def fingerprint(capability):
    clean = {k: v for k, v in capability.items() if k != '_path'}
    return _digest(json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def reusable(path, previous, **context):
    current = validate(path, **context)
    if fingerprint(current) != fingerprint(previous):
        raise ValueError('Capability cambiada; requiere nueva autorización')
    return current
