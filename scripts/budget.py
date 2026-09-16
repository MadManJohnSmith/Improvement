#!/usr/bin/env python3
"""Límites durables locales (intentos/coste/tiempo); no concede autoridad ni mide semántica.

Registro de eventos inmutable en estado externo: cada reserva se escribe con
creación exclusiva (enlace temporal) antes de consumir, de modo que un corte o
reinicio nunca reinicia el gasto ni puede duplicar un evento. El consumo se
recalcula desde los eventos persistidos; los límites se fijan una sola vez y
una reapertura con límites distintos falla cerrada. La reserva se declara antes
del trabajo (dirección conservadora: un corte puede sobrecontar, nunca
subcontar). Almacén local confiable de un solo escritor; concurrencia hostil
requiere coordinación del Host. La corrección de coste/tiempo declarados es
responsabilidad del caller; este módulo no observa procesos reales.
"""
import hashlib
import json
import os
import secrets
import tempfile

from pathlib import Path

from onboard import checked

DIMENSIONS = ('attempts', 'cost', 'seconds')
MAX_EVENT = 4096


class BudgetExhausted(ValueError):
    """El gasto acumulado más la reserva excede un límite persistido."""


def _quantity(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError('Cantidad inválida: ' + label)
    return value


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


class Ledger:
    """Presupuesto acumulativo persistido; límites inmutables y eventos exclusivos."""

    def __init__(self, root, *, attempts=None, cost=None, seconds=None):
        self.root = checked(root)
        if self.root.exists() and (not self.root.is_dir() or self.root.is_symlink()):
            raise ValueError('Raíz de presupuesto inválida')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        provided = {'attempts': attempts, 'cost': cost, 'seconds': seconds}
        for name, value in provided.items():
            if value is not None:
                _quantity(value, name)
        stored = self._read(self.root / 'limits.json') if (self.root / 'limits.json').exists() else None
        if stored is None:
            if any(value is None for value in provided.values()):
                raise ValueError('Límites completos requeridos al crear el presupuesto')
            self._write(self.root / 'limits.json', {'kind': 'budget-limits', **provided})
            stored = dict(provided)
        else:
            try:
                stored = {name: stored[name] for name in DIMENSIONS}
            except KeyError as error:
                raise ValueError('Límites persistidos incompletos') from error
            if any(value is not None and value != stored[name] for name, value in provided.items()):
                raise ValueError('Límites persistidos no coinciden; no se reinician ni rebajan')
        self.limits = stored

    def usage(self):
        """Totales recalculados desde los eventos persistidos; detecta alteraciones."""
        totals = {name: 0 for name in DIMENSIONS}
        for path in sorted(self.root.glob('e-*.json')):
            event = self._read(path)
            if event.get('kind') != 'budget-event':
                raise ValueError('Evento de presupuesto inválido')
            for name in DIMENSIONS:
                totals[name] += _quantity(event.get(name), name)
        return totals

    def reserve(self, *, attempts=0, cost=0, seconds=0):
        """Reserva gasto antes del trabajo; falla cerrada sin escribir si excede."""
        requested = {'attempts': _quantity(attempts, 'attempts'),
                     'cost': _quantity(cost, 'cost'),
                     'seconds': _quantity(seconds, 'seconds')}
        usage = self.usage()
        for name in DIMENSIONS:
            if usage[name] + requested[name] > self.limits[name]:
                raise BudgetExhausted('Presupuesto agotado: ' + name)
        envelope = self._write(self.root / ('e-' + secrets.token_urlsafe(12) + '.json'),
                               {'kind': 'budget-event', **requested})
        return {'usage': {name: usage[name] + requested[name] for name in DIMENSIONS},
                'event_id': envelope['event_id']}

    def _write(self, path, payload):
        envelope = {'version': 1, 'event_id': path.stem, 'payload': payload}
        envelope['content_sha256'] = hashlib.sha256(_json_bytes(envelope)).hexdigest()
        raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('Registro de presupuesto alterado')
            return envelope
        with tempfile.NamedTemporaryFile(dir=self.root, prefix='.budget-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != raw:
                        raise ValueError('Registro de presupuesto alterado')
            finally:
                temporary.unlink()
        return envelope

    def _read(self, path):
        raw = checked(path).read_bytes()
        if len(raw) > MAX_EVENT:
            raise ValueError('Registro de presupuesto demasiado grande')
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('payload'), dict):
            raise ValueError('Registro de presupuesto inválido')
        try:
            content = {key: value[key] for key in ('version', 'event_id', 'payload')}
        except KeyError as error:
            raise ValueError('Registro de presupuesto alterado') from error
        if value.get('content_sha256') != hashlib.sha256(_json_bytes(content)).hexdigest():
            raise ValueError('Registro de presupuesto alterado')
        return value['payload']
