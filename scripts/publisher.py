#!/usr/bin/env python3
"""Publicación local acotada de recibos; no es un publicador Host ni sandbox."""
import hashlib
import json
import os
import re
import secrets
import tempfile

from pathlib import Path

import missions

from onboard import FRAMEWORK, checked

MAX_PAYLOAD = 8192
MAX_RECEIPT = 16384
MAX_RECORDS = 16
MAX_TEXT = 3000


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
        self._roles = {}
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
        if len(raw) > MAX_RECEIPT:
            raise ValueError('Recibo demasiado grande')
        if not path.exists() and len(tuple(self.root.glob('*.json'))) >= MAX_RECORDS:
            raise ValueError('Límite de registros alcanzado')
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise ValueError('Registro inválido')
            existing = path.read_bytes()
            if _digest(existing) != digest:
                raise ValueError('Conflicto de registro')
            return json.loads(existing)
        # ponytail: almacén local confiable; concurrencia hostil requiere Host.
        with tempfile.NamedTemporaryFile(dir=self.root, prefix='.receipt-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    existing = self.resolve(record_id)
                    if existing != envelope:
                        raise ValueError('Conflicto de registro')
                    return existing
            finally:
                temporary.unlink()
        return envelope

    def _batch_key(self, batch_id, suffix):
        if not isinstance(batch_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', batch_id):
            raise ValueError('ID de lote inválido')
        return batch_id + '-' + suffix

    def open_batch(self, caller, authorization, objective, batch_id=None):
        if not isinstance(caller, str) or not caller or not isinstance(authorization, str) or not authorization:
            raise ValueError('Identidad y autorización requeridas')
        if not isinstance(objective, str) or not objective.strip() or len(objective) > MAX_TEXT:
            raise ValueError('Objetivo inválido')
        batch_id = batch_id or 'b_' + secrets.token_urlsafe(18)
        key = self._batch_key(batch_id, 'open')
        receipt = self.publish(caller, authorization, {
            'type': 'open', 'batch_id': batch_id, 'objective': objective,
            'status': 'OPEN', 'records': [], 'gaps': [],
        }, key)
        return {'batch_id': batch_id, 'record_id': key, 'receipt': receipt}

    def _read_batch(self, caller, authorization, batch_id):
        opened = self.resolve(self._batch_key(batch_id, 'open'))
        if opened.get('caller') != caller or opened.get('authorization') != authorization:
            raise ValueError('Propietario de lote incorrecto')
        return opened

    def publish_batch_record(self, caller, authorization, batch_id, record_type, payload, record_id=None):
        if record_type not in ('evidence', 'task'):
            raise ValueError('Tipo de registro inválido')
        opened = self._read_batch(caller, authorization, batch_id)
        close_path = self.root / (self._batch_key(batch_id, 'close') + '.json')
        if close_path.exists() or close_path.is_symlink():
            raise ValueError('Lote cerrado')
        if len(opened['payload'].get('records', [])) >= MAX_RECORDS:
            raise ValueError('Límite de registros alcanzado')
        if not isinstance(payload, dict):
            raise ValueError('Payload de registro inválido')
        record_id = record_id or 'r_' + secrets.token_urlsafe(18)
        record = self.publish(caller, authorization, {
            'type': record_type, 'batch_id': batch_id, 'payload': payload,
        }, self._batch_key(batch_id, record_id))
        return {'record_id': self._batch_key(batch_id, record_id), 'receipt': record}

    def close_batch(self, caller, authorization, batch_id, status, record_ids, gaps):
        opened = self._read_batch(caller, authorization, batch_id)
        if opened['payload'].get('status') != 'OPEN':
            raise ValueError('Lote cerrado')
        if status not in ('COMPLETE', 'PARTIAL') or not isinstance(record_ids, list) or len(record_ids) > MAX_RECORDS or len(set(record_ids)) != len(record_ids):
            raise ValueError('Cierre inválido')
        if not isinstance(gaps, list) or len(gaps) > MAX_RECORDS or any(not isinstance(g, str) or not g.strip() or len(g) > MAX_TEXT for g in gaps):
            raise ValueError('Gaps inválidos')
        records = []
        types = set()
        for record_id in record_ids:
            if not isinstance(record_id, str) or not record_id.startswith(batch_id + '-'):
                raise ValueError('Referencia extranjera')
            record = self.resolve(record_id)
            if record['caller'] != caller or record['authorization'] != authorization or record['payload'].get('batch_id') != batch_id:
                raise ValueError('Registro ajeno')
            if record['payload'].get('type') not in ('evidence', 'task'):
                raise ValueError('Registro inválido')
            records.append({'record_id': record_id, 'sha256': record['content_sha256']})
            types.add(record['payload']['type'])
        if status == 'COMPLETE' and (gaps or types != {'evidence', 'task'}):
            raise ValueError('Entrega incompleta')
        if status == 'COMPLETE':
            record_map = {item['record_id']: self.resolve(item['record_id']) for item in records}
            for item in records:
                record = record_map[item['record_id']]
                if record['payload']['type'] == 'task':
                    evidence_id = record['payload']['payload'].get('evidence_id')
                    if evidence_id not in record_map or record_map[evidence_id]['payload']['type'] != 'evidence':
                        raise ValueError('Tarea sin evidencia')
        if status == 'PARTIAL' and not gaps:
            raise ValueError('Entrega parcial requiere gaps')
        close_id = self._batch_key(batch_id, 'close')
        try:
            existing = self.resolve(close_id)
        except ValueError:
            existing = None
        payload = {
            'type': 'receipt', 'batch_id': batch_id, 'status': status,
            'records': records, 'gaps': gaps, 'open': opened['content_sha256'],
        }
        if existing is not None:
            if existing['caller'] != caller or existing['authorization'] != authorization or existing['payload'] != payload:
                raise ValueError('Conflicto de cierre')
            return existing
        closed = self.publish(caller, authorization, payload, close_id)
        return closed

    def bind_role(self, caller, role):
        if not isinstance(caller, str) or not caller or role not in ('executor', 'qa', 'auditor'):
            raise ValueError('Binding inválido')
        current = self._roles.get(caller)
        if current is not None and current != role:
            raise ValueError('Caller ya ligado a otro rol')
        self._roles[caller] = role
        return {'caller': caller, 'role': role}

    def report_stage(self, caller, authorization, batch_id, stage, status, evidence, actor_id):
        if stage not in ('executor', 'qa', 'auditor'):
            raise ValueError('Etapa inválida')
        # Role bindings are advisory until Host ownership can authorize multiple callers per batch.
        allowed = {
            'executor': {'CANDIDATE', 'FAILED'},
            'qa': {'VERIFIED', 'UNVERIFIED', 'REJECTED'},
            'auditor': {'ACCEPTED', 'RETAINED'},
        }
        if status not in allowed[stage] or not isinstance(evidence, str) or not evidence.strip() or len(evidence) > MAX_TEXT:
            raise ValueError('Estado o evidencia inválidos')
        if not isinstance(actor_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', actor_id):
            raise ValueError('Actor inválido')
        self._read_batch(caller, authorization, batch_id)
        try:
            closed = self.resolve(self._batch_key(batch_id, 'close'))
        except ValueError as error:
            raise ValueError('Requiere entrega completa') from error
        self.resolve_handoff(self.handoff(closed['record_id']))
        payload = closed['payload']
        if payload.get('type') != 'receipt' or payload.get('status') != 'COMPLETE':
            raise ValueError('Requiere entrega completa')
        existing_key = self._batch_key(batch_id, stage)
        try:
            existing = self.resolve(existing_key)
        except ValueError:
            existing = None
        if stage == 'qa':
            executor = self._require_stage(batch_id, 'executor', 'CANDIDATE')
            if executor['payload'].get('actor_id') == actor_id:
                raise ValueError('QA requiere actor distinto')
        if stage == 'auditor':
            qa = self._require_stage(batch_id, 'qa')
            executor = self._require_stage(batch_id, 'executor', 'CANDIDATE')
            if actor_id in (qa['payload'].get('actor_id'), executor['payload'].get('actor_id')):
                raise ValueError('Auditor requiere actor distinto')
            if status == 'ACCEPTED' and qa['payload']['status'] != 'VERIFIED':
                raise ValueError('Aceptación bloqueada por QA')
        if status in ('CANDIDATE', 'VERIFIED', 'ACCEPTED'):
            references = {item['record_id'] for item in payload['records']}
            if evidence not in references:
                raise ValueError('Etapa requiere evidencia del lote')
            if not any(self.resolve(item)['payload'].get('type') == 'task' and
                       self.resolve(item)['payload']['payload'].get('evidence_id') == evidence
                       for item in references):
                raise ValueError('Evidencia sin tarea enlazada')
            artifact = self.resolve(evidence)['payload']
            if artifact.get('type') != 'evidence':
                raise ValueError('Referencia no es evidencia')
            artifact = artifact['payload']
            try:
                for name in ('task', 'result'):
                    if missions.digest(checked(artifact[name + '_ref']).read_bytes()) != artifact.get(name + '_sha256'):
                        raise ValueError('Artefacto de misión alterado')
                verdict = missions.verify(artifact['task_ref'], artifact['result_ref'])
            except (OSError, KeyError, TypeError) as error:
                raise ValueError('Artefactos de misión ausentes o inválidos') from error
            if not verdict.startswith('ACCEPTED:'):
                raise ValueError('Misión no aceptada')
            if stage != 'executor' and executor['payload']['evidence'] != evidence:
                raise ValueError('Etapa de otro candidato')
            if stage == 'auditor' and qa['payload']['evidence'] != evidence:
                raise ValueError('QA de otro candidato')
        stage_payload = {'type': 'stage', 'batch_id': batch_id, 'stage': stage, 'status': status, 'evidence': evidence, 'actor_id': actor_id}
        if existing is not None:
            if existing['caller'] != caller or existing['authorization'] != authorization or existing['payload'] != stage_payload:
                raise ValueError('Conflicto de estado')
            return existing
        return self.publish(caller, authorization, stage_payload, existing_key)

    def _require_stage(self, batch_id, stage, status=None):
        receipt = self.resolve(self._batch_key(batch_id, stage))
        if receipt['payload'].get('type') != 'stage' or (status and receipt['payload'].get('status') != status):
            raise ValueError('Transición de etapa inválida')
        return receipt

    def handoff(self, record_id):
        if not isinstance(record_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', record_id):
            raise ValueError('ID inválido')
        receipt = self.resolve(record_id)
        if receipt.get('payload', {}).get('type') != 'receipt' or receipt['payload'].get('status') != 'COMPLETE':
            raise ValueError('Recibo no entregable')
        return 'INICIO_LOTE: {"receipt_id":"' + record_id + '"}'

    def resolve_handoff(self, text):
        if not isinstance(text, str) or len(text) > 160:
            raise ValueError('Handoff inválido')
        match = re.fullmatch(r'INICIO_LOTE: \{"receipt_id":"([A-Za-z0-9_-]{1,80})"\}', text)
        if not match:
            raise ValueError('Handoff inválido')
        receipt = self.resolve(match.group(1))
        payload = receipt.get('payload', {})
        if payload.get('type') == 'receipt' and payload.get('status') == 'COMPLETE':
            for reference in payload.get('records', []):
                record = self.resolve(reference['record_id'])
                if record.get('content_sha256') != reference.get('sha256'):
                    raise ValueError('Referencia alterada')
            return receipt
        raise ValueError('Handoff incompleto')

    def resolve(self, record_id):
        if not isinstance(record_id, str) or not record_id or not all(c.isalnum() or c in '_-' for c in record_id):
            raise ValueError('ID inválido')
        path = checked(self.root / (record_id + '.json'))
        if not path.is_file():
            raise ValueError('Recibo ausente o inválido')
        try:
            raw = path.read_bytes()
        except FileNotFoundError as error:
            raise ValueError('Recibo ausente') from error
        if len(raw) > MAX_RECEIPT:
            raise ValueError('Recibo demasiado grande')
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
