#!/usr/bin/env python3
"""Publicación local acotada de recibos; no es un publicador Host ni sandbox."""
import hashlib
import json
import secrets
from pathlib import Path

from onboard import FRAMEWORK, checked

MAX_PAYLOAD = 8192
MAX_RECORDS = 16


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _external(path):
    path = checked(path)
    if path == FRAMEWORK or FRAMEWORK in path.parents or path in FRAMEWORK.parents:
        raise ValueError('Destino externo requerido')
    return path


def _json(value):
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    except (TypeError, ValueError) as error:
        raise ValueError('Payload JSON inválido') from error
    if len(data) > MAX_PAYLOAD:
        raise ValueError('Payload demasiado grande')
    return data


class Publisher:
    """Almacén externo mínimo con identidad/autorización suministradas por el Host."""

    def __init__(self, root):
        self.root = _external(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ValueError('Destino inválido')

    def publish(self, caller, authorization, payload, record_id=None):
        if not isinstance(caller, str) or not caller or not isinstance(authorization, str) or not authorization:
            raise ValueError('Identidad y autorización requeridas')
        data = _json(payload)
        record_id = record_id or 'r_' + secrets.token_urlsafe(18)
        if not isinstance(record_id, str) or not record_id.isascii() or not 1 <= len(record_id) <= 80:
            raise ValueError('ID inválido')
        if not all(char.isalnum() or char in '_-' for char in record_id):
            raise ValueError('ID inválido')
        envelope = {
            'version': 1, 'record_id': record_id, 'caller': caller,
            'authorization': authorization, 'payload': payload,
        }
        content = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        envelope['content_sha256'] = _digest(content)
        raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
        path = self.root / (record_id + '.json')
        digest = _digest(raw)
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise ValueError('Registro inválido')
            existing = path.read_bytes()
            if _digest(existing) != digest:
                raise ValueError('Conflicto de registro')
            return json.loads(existing)
        try:
            with path.open('xb') as stream:
                stream.write(raw)
        except FileExistsError:
            existing = path.read_bytes()
            if _digest(existing) != digest:
                raise ValueError('Conflicto de registro')
            return json.loads(existing)
        return envelope

    def resolve(self, record_id):
        if not isinstance(record_id, str) or not record_id or not all(c.isalnum() or c in '_-' for c in record_id):
            raise ValueError('ID inválido')
        path = self.root / (record_id + '.json')
        raw = path.read_bytes()
        value = json.loads(raw)
        if value.get('version') != 1 or value.get('record_id') != record_id:
            raise ValueError('Recibo inválido')
        try:
            content = {key: value[key] for key in ('version', 'record_id', 'caller', 'authorization', 'payload')}
        except KeyError as error:
            raise ValueError('Recibo alterado') from error
        if value.get('content_sha256') != _digest(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()):
            raise ValueError('Recibo alterado')
        return value
