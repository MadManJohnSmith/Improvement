#!/usr/bin/env python3
"""Memoria de decisiones por misión (§7 de ARQUITECTURA_FLUJO_AGENTES.md); no concede autoridad.

Almacén externo append-only en `<misión>/decisions`: cada decisión y cada
sustitución se escriben una sola vez con creación exclusiva (enlace temporal)
y digest SHA-256 del contenido, de modo que un corte no deja escrituras
parciales ni reordena historia. Sustituir no borra ni reescribe: añade un
marcador nuevo que deja la decisión original sin efecto vigente; el historial
completo permanece verificado. La identidad del almacén se fija una sola vez y
reabrir con identidad distinta o alterada falla cerrado, igual que leer un
registro cuyos bytes no verifican. Almacén local confiable de un solo escritor;
concurrencia hostil requiere coordinación del Host. authorization_ref declara
la autoridad del caller (sin ella no se sustituye); este módulo no la comprueba.
"""
import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
MAX_RECORD = 65536
ROOT = Path(__file__).resolve().parents[1]


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _checked(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Ruta con enlace simbólico')
    return path


def _external(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('El almacén de decisiones debe ser externo al framework')
    return path


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Texto requerido: ' + label)
    return value


def _text_list(value, label, *, required):
    if not isinstance(value, list) or (required and not value):
        raise ValueError('Lista inválida: ' + label)
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError('Elementos de texto requeridos: ' + label)
    return list(value)


def _identifier(value, label):
    if not isinstance(value, str) or not value or '/' in value or '\\' in value or value in ('.', '..'):
        raise ValueError('Identificador inválido: ' + label)
    return value


def _validated(motive, alternatives, affected_units, contract_ref, authorization_ref):
    """Valida los campos de una decisión antes de cualquier escritura."""
    motive = _text(motive, 'motive')
    alternatives = _text_list(alternatives, 'alternatives', required=False)
    affected_units = _text_list(affected_units, 'affected_units', required=True)
    authorization_ref = _text(authorization_ref, 'authorization_ref')
    if contract_ref is not None:
        contract_ref = _text(contract_ref, 'contract_ref')
    return motive, alternatives, affected_units, contract_ref, authorization_ref


def create(mission_dir, identity):
    """Abre o crea el almacén de decisiones de una misión; la identidad es exclusiva."""
    return DecisionStore(mission_dir, identity)


class DecisionStore:
    """Memoria append-only de decisiones de una misión; identidad inmutable."""

    def __init__(self, mission_dir, identity):
        _text(identity, 'identity')
        mission_dir = _external(mission_dir)
        if mission_dir.exists() and not mission_dir.is_dir():
            raise ValueError('Directorio de misión inválido')
        mission_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root = mission_dir / 'decisions'
        if self.root.exists() and (not self.root.is_dir() or self.root.is_symlink()):
            raise ValueError('Raíz de decisiones inválida')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.identity = identity
        identity_path = self.root / 'identity.json'
        if identity_path.exists():
            stored = self._read(identity_path)['payload']
            if stored.get('kind') != 'decision-store' or stored.get('identity') != identity:
                raise ValueError('Identidad del almacén distinta o alterada; no se reabre')
        else:
            self._write(identity_path, 'identity', {'kind': 'decision-store', 'identity': identity})

    def record(self, motive, alternatives, affected_units, contract_ref=None, authorization_ref=None):
        """Registra una decisión VIGENTE nueva con digest; valida todo antes de escribir."""
        motive, alternatives, affected_units, contract_ref, authorization_ref = _validated(
            motive, alternatives, affected_units, contract_ref, authorization_ref)
        records, _ = self._load()
        decision_id = 'D-' + str(len(records) + 1).rjust(4, '0') + '-' + secrets.token_urlsafe(9)
        payload = {'kind': 'decision', 'decision_id': decision_id, 'version': VERSION,
                   'motive': motive, 'alternatives': alternatives, 'affected_units': affected_units,
                   'status': 'VIGENTE', 'authorization_ref': authorization_ref,
                   'created_at': datetime.now(timezone.utc).isoformat()}
        if contract_ref is not None:
            payload['contract_ref'] = contract_ref
        self._write(self.root / ('d-' + decision_id + '.json'), decision_id, payload)
        return self.get(decision_id)

    def supersede(self, decision_id, replacement_id, authorization_ref=None):
        """Deja una decisión sin efecto vigente con un marcador nuevo; sin autorización no sustituye."""
        decision_id = _identifier(decision_id, 'decision_id')
        replacement_id = _identifier(replacement_id, 'replacement_id')
        _text(authorization_ref, 'authorization_ref')
        records, supersedes = self._load()
        if decision_id not in records:
            raise ValueError('Decisión a sustituir ausente')
        if replacement_id == decision_id or replacement_id not in records:
            raise ValueError('Reemplazo ausente o inválido')
        if decision_id in supersedes:
            raise ValueError('Decisión ya sustituida')
        payload = {'kind': 'decision-supersede', 'decision_id': decision_id,
                   'replacement_id': replacement_id, 'authorization_ref': authorization_ref,
                   'created_at': datetime.now(timezone.utc).isoformat()}
        self._write(self.root / ('s-' + decision_id + '.json'), decision_id, payload)
        return self.get(decision_id)

    def get(self, decision_id):
        """Vista efectiva de una decisión (status y replacement_ref derivados); KeyError si ausente."""
        decision_id = _identifier(decision_id, 'decision_id')
        views = self._view(*self._load())
        if decision_id not in views:
            raise KeyError('Decisión ausente: ' + decision_id)
        return views[decision_id]

    def get_for_units(self, units):
        """Decisiones VIGENTES pertinentes a las unidades dadas, en orden de creación."""
        if isinstance(units, str) or not isinstance(units, (list, tuple, set, frozenset)) or not units:
            raise ValueError('Unidades afectadas inválidas')
        wanted = {_text(unit, 'unit') for unit in units}
        views = self._view(*self._load())
        ordered = sorted(views.values(), key=lambda view: (view['created_at'], view['decision_id']))
        return [view for view in ordered
                if view['status'] == 'VIGENTE' and wanted.intersection(view['affected_units'])]

    def verify(self):
        """Recomputa identidad y digests de todo el almacén; falla cerrada si algo no verifica."""
        stored = self._read(self.root / 'identity.json')['payload']
        if stored.get('kind') != 'decision-store' or stored.get('identity') != self.identity:
            raise ValueError('Identidad del almacén distinta o alterada')
        records, supersedes = self._load()
        return {'kind': 'decision-store-verify', 'decisions': len(records), 'supersedes': len(supersedes)}

    def _load(self):
        records = {}
        for path in sorted(self.root.glob('d-*.json')):
            envelope = self._read(path)
            payload = envelope['payload']
            decision_id = _identifier(payload.get('decision_id'), 'decision_id')
            if payload.get('kind') != 'decision' or envelope['event_id'] != decision_id:
                raise ValueError('Registro de decisión inválido')
            if payload.get('status') != 'VIGENTE' or payload.get('version') != VERSION:
                raise ValueError('Registro de decisión inválido')
            _text(payload.get('created_at'), 'created_at')
            _validated(payload.get('motive'), payload.get('alternatives'), payload.get('affected_units'),
                       payload.get('contract_ref'), payload.get('authorization_ref'))
            if decision_id in records:
                raise ValueError('Decisión duplicada')
            records[decision_id] = payload
        supersedes = {}
        for path in sorted(self.root.glob('s-*.json')):
            payload = self._read(path)['payload']
            if payload.get('kind') != 'decision-supersede':
                raise ValueError('Marcador de sustitución inválido')
            decision_id = _identifier(payload.get('decision_id'), 'decision_id')
            replacement_id = _identifier(payload.get('replacement_id'), 'replacement_id')
            _text(payload.get('authorization_ref'), 'authorization_ref')
            _text(payload.get('created_at'), 'created_at')
            if decision_id in supersedes or decision_id not in records:
                raise ValueError('Sustitución duplicada o de decisión ausente')
            if replacement_id == decision_id or replacement_id not in records:
                raise ValueError('Reemplazo de sustitución ausente o inválido')
            supersedes[decision_id] = payload
        return records, supersedes

    def _view(self, records, supersedes):
        views = {}
        for decision_id, payload in records.items():
            view = dict(payload)
            marker = supersedes.get(decision_id)
            if marker is not None:
                view['status'] = 'SUSTITUIDA'
                view['replacement_ref'] = marker['replacement_id']
            views[decision_id] = view
        return views

    def _write(self, path, event_id, payload):
        envelope = {'version': VERSION, 'event_id': event_id, 'payload': payload}
        envelope['content_sha256'] = hashlib.sha256(_json_bytes(envelope)).hexdigest()
        raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('Registro de decisión ya existe con otro contenido')
            return envelope
        with tempfile.NamedTemporaryFile(dir=self.root, prefix='.decision-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != raw:
                        raise ValueError('Registro de decisión ya existe con otro contenido')
            finally:
                temporary.unlink()
        return envelope

    def _read(self, path):
        raw = _checked(path).read_bytes()
        if len(raw) > MAX_RECORD:
            raise ValueError('Registro de decisión demasiado grande')
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('version') != VERSION
                or not isinstance(value.get('payload'), dict)):
            raise ValueError('Registro de decisión inválido')
        try:
            content = {key: value[key] for key in ('version', 'event_id', 'payload')}
        except KeyError as error:
            raise ValueError('Registro de decisión alterado') from error
        if (not isinstance(content['event_id'], str)
                or value.get('content_sha256') != hashlib.sha256(_json_bytes(content)).hexdigest()):
            raise ValueError('Registro de decisión alterado')
        return value
