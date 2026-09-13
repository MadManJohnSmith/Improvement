#!/usr/bin/env python3
"""Controlador Host (M3): bucle mecánico sin LLM sobre una cola durable.

Mantiene estado exclusivo en un directorio de misión externo al framework:
mission.json (mandato: identidad y límites), queue.json (cola canónica),
events.jsonl (diario append-only con checkpoint en cada transición), locks/
(flock global "un solo controlador vivo" y flock por unidad) y budget/
(presupuesto durable de budget.Ledger). El turno de cada unidad se lanza con
un callable inyectado por el caller (el rig en producción; un fake
determinista en pruebas): este módulo no ejecuta modelos, no interpreta
semántica y no concede autoridad; verifica hashes con missions.digest,
publica el lote del publicador en un almacén por unidad y registra
UNIT_DONE | UNIT_RETAINED con causa.

Reconciliación (contrato especificado y probado en tests/test_recovery_durable.py):
al arrancar un controlador nuevo, las unidades IN_FLIGHT se re-marcan PENDING
(reconcile_on_start); el relanzamiento del turno queda a cargo del caller; el
presupuesto acumulado no se reinicia y ninguna escritura se duplica: los
lotes del publicador son idempotentes por contenido y el lock global impide
dos controladores vivos.
"""
import fcntl
import json
import os
import re
import signal
import tempfile
import time

from pathlib import Path

import missions
from budget import Ledger
from publisher import Publisher

UNIT_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,46}\Z')
SHA256_PATTERN = re.compile(r'[0-9a-f]{64}\Z')
STATES = ('PENDING', 'IN_FLIGHT', 'DONE', 'RETAINED')
REQUIRED_UNIT_KEYS = ('unit_id', 'task_ref', 'result_ref', 'task_sha256', 'result_sha256', 'state')
OPTIONAL_UNIT_KEYS = ('objective', 'cost', 'seconds', 'retained_cause')
DIMENSIONS = ('attempts', 'cost', 'seconds')
MAX_REF = 1024
MAX_OBJECTIVE = 512
MAX_CAUSE = 2000


class HostError(RuntimeError):
    """Fallo cerrado del controlador (secuencia, lock o estado inválido)."""


class ControllerAlive(HostError):
    """Ya existe otro controlador vivo con el lock global de la misión."""


def _quantity(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError('Cantidad inválida: ' + label)
    return value


def _check_limits(limits):
    if not isinstance(limits, dict) or set(limits) != set(DIMENSIONS):
        raise ValueError('Límites requieren attempts, cost y seconds')
    return {name: _quantity(limits[name], name) for name in DIMENSIONS}


def _validate_unit(unit):
    if not isinstance(unit, dict):
        raise ValueError('Unidad debe ser un objeto')
    unknown = sorted(set(unit) - set(REQUIRED_UNIT_KEYS) - set(OPTIONAL_UNIT_KEYS))
    if unknown:
        raise ValueError('Campos desconocidos en unidad: ' + ', '.join(unknown))
    missing = sorted(set(REQUIRED_UNIT_KEYS) - set(unit))
    if missing:
        raise ValueError('Faltan campos en unidad: ' + ', '.join(missing))
    if unit['state'] not in STATES:
        raise ValueError('Estado de unidad inválido: ' + repr(unit['state']))
    if not isinstance(unit['unit_id'], str) or not UNIT_PATTERN.fullmatch(unit['unit_id']):
        raise ValueError('unit_id inválido (letras, dígitos, _ y -; hasta 47 caracteres)')
    for key in ('task_ref', 'result_ref'):
        ref = unit[key]
        if not isinstance(ref, str) or not ref or len(ref) > MAX_REF:
            raise ValueError('Referencia inválida: ' + key)
    for key in ('task_sha256', 'result_sha256'):
        value = unit[key]
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise ValueError('sha256 inválido: ' + key)
    objective = unit.get('objective')
    if objective is not None and (not isinstance(objective, str) or not objective.strip()
                                  or len(objective) > MAX_OBJECTIVE):
        raise ValueError('Objetivo inválido')
    for key in ('cost', 'seconds'):
        if unit.get(key) is not None:
            _quantity(unit[key], key)
    cause = unit.get('retained_cause')
    if cause is not None and (not isinstance(cause, str) or not cause or len(cause) > MAX_CAUSE):
        raise ValueError('Causa de retención inválida')


class HostController:
    """Consume una cola durable lanzando turnos inyectados, sin LLM propio."""

    def __init__(self, mission_dir):
        self.mission_dir = Path(mission_dir)
        if self.mission_dir.is_symlink() or (self.mission_dir.exists() and not self.mission_dir.is_dir()):
            raise ValueError('Directorio de misión inválido')
        self.mission_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.locks_dir = self.mission_dir / 'locks'
        self.locks_dir.mkdir(mode=0o700, exist_ok=True)
        self._mission_path = self.mission_dir / 'mission.json'
        self._queue_path = self.mission_dir / 'queue.json'
        self._events_path = self.mission_dir / 'events.jsonl'
        self._budget_root = self.mission_dir / 'budget'
        self._published_root = self.mission_dir / 'publish'
        # Lock global exclusivo y no bloqueante: solo un controlador vivo.
        self._controller_fd = os.open(self.locks_dir / 'controller.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._controller_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._controller_fd)
            self._controller_fd = None
            raise ControllerAlive('Ya existe un controlador vivo para esta misión')
        self._unit_fds = {}
        self._descendants = []
        self._released = False
        self._events = None
        self._seq = 0
        try:
            self._mandate = self._load_mandate()
            self.budget = (Ledger(self._budget_root)
                           if (self._budget_root / 'limits.json').exists() else None)
            if (self._mandate is not None and self.budget is not None
                    and self.budget.limits != self._mandate['limits']):
                raise ValueError('Límites del mandato no coinciden con el presupuesto persistido')
            self._queue = self._load_queue()
            self._seq = self._count_events()
            self._events = open(self._events_path, 'a', encoding='utf-8')
            self._event('CONTROLLER_STARTED', pid=os.getpid())
        except BaseException:
            self._close_locks()
            raise

    # -- mandato -----------------------------------------------------------

    def register_mandate(self, identity, limits, authorization='host-mandate'):
        """Crea el mandato con creación exclusiva; reabrir distinto falla cerrado."""
        self._ensure_active()
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
            raise ValueError('Identidad inválida')
        if not isinstance(authorization, str) or not authorization or len(authorization) > 128:
            raise ValueError('Autorización inválida')
        limits = _check_limits(limits)
        if self._mandate is not None:
            stored = self._mandate
            if (stored['identity'], stored['authorization'], stored['limits']) != (identity, authorization, limits):
                raise ValueError('Mandato existente distinto; no se reemplaza')
            if self.budget is not None and self.budget.limits != limits:
                raise ValueError('Límites persistidos no coinciden con el mandato')
            return {'created': False}
        # Primero el ledger: falla cerrado si el presupuesto persistido difiere.
        ledger = Ledger(self._budget_root, attempts=limits['attempts'],
                        cost=limits['cost'], seconds=limits['seconds'])
        try:
            missions.save(self._mission_path, {
                'version': 1, 'kind': 'host-mission', 'identity': identity,
                'authorization': authorization, 'limits': dict(limits),
                'created_at': time.time()})
        except FileExistsError:
            raise ValueError('Mandato ya registrado')
        self.budget = ledger
        self._mandate = {'identity': identity, 'authorization': authorization, 'limits': dict(limits)}
        self._event('MANDATE_REGISTERED', identity=identity, limits=dict(limits))
        return {'created': True}

    # -- cola --------------------------------------------------------------

    def enqueue(self, unit):
        """Encola una unidad validada; duplicados y malformados no escriben nada."""
        self._ensure_active()
        if self._mandate is None:
            raise HostError('Mandato no registrado')
        if not isinstance(unit, dict):
            raise ValueError('Unidad debe ser un objeto')
        entry = dict(unit)
        for key in ('state', 'retained_cause'):
            if key in entry:
                raise ValueError('Campo gestionado por el controlador: ' + key)
        entry['state'] = 'PENDING'
        _validate_unit(entry)
        if any(existing['unit_id'] == entry['unit_id'] for existing in self._queue['units']):
            raise ValueError('Unidad duplicada: ' + entry['unit_id'])
        self._queue['units'].append(entry)
        try:
            self._save_queue()
        except BaseException:
            self._queue['units'].pop()
            raise
        self._event('UNIT_ENQUEUED', unit=entry['unit_id'],
                    task_sha256=entry['task_sha256'], result_sha256=entry['result_sha256'])
        return {'unit_id': entry['unit_id'], 'state': 'PENDING'}

    def units(self):
        """Vista de solo lectura de la cola canónica (copias por unidad)."""
        return [dict(unit) for unit in self._queue['units']]

    # -- reconciliación ----------------------------------------------------

    def reconcile_on_start(self):
        """Re-marca IN_FLIGHT como PENDING de forma idempotente; presupuesto intacto."""
        self._ensure_active()
        if self._mandate is None:
            raise HostError('Mandato no registrado')
        reconciled = []
        for unit in self._queue['units']:
            if unit['state'] == 'IN_FLIGHT':
                unit['state'] = 'PENDING'
                reconciled.append(unit['unit_id'])
        if not reconciled:
            return {'reconciled': []}
        self._save_queue()
        for unit_id in reconciled:
            self._event('UNIT_RECONCILED', unit=unit_id)
        return {'reconciled': reconciled}

    # -- consumo -----------------------------------------------------------

    def run_next(self, turn_launcher, inject=None):
        """Ejecuta el pipeline de la siguiente unidad PENDING.

        turn_launcher(unit) -> dict: lanza el turno (rig en producción, fake en
        pruebas) y deja los artefactos en task_ref/result_ref con los sha256
        encolados; el dict devuelto se journaliza como recibo del turno.
        Checkpoints en events.jsonl: TURN_STARTED -> CHECK_RECEIVED (hashes de
        task/result con missions.digest) -> PUBLISHED (lote del publicador en
        almacén por unidad) -> UNIT_DONE | UNIT_RETAINED con causa. Excepción
        del launcher -> UNIT_RETAINED y candidato preservado. Agotamiento de
        presupuesto -> BudgetExhausted propagado con la unidad PENDING y sin
        escrituras. `inject` es el punto de caída simulada (solo arnés).
        """
        self._ensure_active()
        if self._mandate is None:
            raise HostError('Mandato no registrado')
        if not callable(turn_launcher):
            raise ValueError('turn_launcher debe ser callable')
        if any(unit['state'] == 'IN_FLIGHT' for unit in self._queue['units']):
            raise HostError('Hay unidades en vuelo sin reconciliar; llamar reconcile_on_start() o cancel()')
        unit = next((u for u in self._queue['units'] if u['state'] == 'PENDING'), None)
        if unit is None:
            return None
        unit_id = unit['unit_id']
        # Reserva conservadora antes de cualquier trabajo o escritura de estado.
        self.budget.reserve(attempts=1,
                            cost=unit['cost'] if unit.get('cost') is not None else 0,
                            seconds=unit['seconds'] if unit.get('seconds') is not None else 0)
        self._lock_unit(unit_id)
        unit['state'] = 'IN_FLIGHT'
        self._save_queue()
        self._event('TURN_STARTED', unit=unit_id)
        if inject is not None:
            inject('turn_started')
        try:
            receipt = turn_launcher(self._unit_view(unit))
            if not isinstance(receipt, dict):
                raise ValueError('recibo de turno no es un objeto')
            self._check_received(unit)
        except Exception as error:
            return self._retain(unit, 'CHECK_RECEIVED fallido: ' + type(error).__name__ + ': ' + str(error))
        self._event('CHECK_RECEIVED', unit=unit_id, turn_receipt=receipt)
        if inject is not None:
            inject('check_received')
        try:
            batch_id = self._publish(unit)
        except Exception as error:
            return self._retain(unit, 'PUBLISHED fallido: ' + type(error).__name__ + ': ' + str(error))
        self._event('PUBLISHED', unit=unit_id, batch_id=batch_id)
        if inject is not None:
            inject('published')
        unit['state'] = 'DONE'
        self._save_queue()
        self._event('UNIT_DONE', unit=unit_id, batch_id=batch_id)
        self._unlock_unit(unit_id)
        return {'unit_id': unit_id, 'outcome': 'UNIT_DONE', 'batch_id': batch_id}

    def run_all(self, turn_launcher, inject=None):
        """Bucle sin LLM: consume la cola hasta vaciarla; BudgetExhausted propaga."""
        summary = {'done': [], 'retained': []}
        while True:
            outcome = self.run_next(turn_launcher, inject=inject)
            if outcome is None:
                return summary
            key = 'done' if outcome['outcome'] == 'UNIT_DONE' else 'retained'
            summary[key].append(outcome['unit_id'])

    # -- cancelación -------------------------------------------------------

    def track_descendant(self, process):
        """Registra un proceso local del turno para que cancel() mate su grupo.

        El controlador no lanza procesos por sí mismo; en las pruebas no hay
        descendientes (no-op). Los descendientes remotos quedan fuera de la
        capacidad aceptada y son responsabilidad del caller.
        """
        if not hasattr(process, 'pid') or not isinstance(getattr(process, 'pid'), int):
            raise ValueError('Descendiente inválido')
        self._descendants.append(process)
        return len(self._descendants)

    def cancel(self):
        """Marca la unidad en vuelo como RETAINED, mata descendientes locales,
        libera locks y conserva el presupuesto; deja el estado recuperable."""
        self._ensure_active()
        if self._mandate is None:
            raise HostError('Mandato no registrado')
        cause = 'cancelado por el operador'
        retained = [unit['unit_id'] for unit in self._queue['units'] if unit['state'] == 'IN_FLIGHT']
        if retained:
            for unit in self._queue['units']:
                if unit['state'] == 'IN_FLIGHT':
                    unit['state'] = 'RETAINED'
                    unit['retained_cause'] = cause
            self._save_queue()
            for unit_id in retained:
                self._event('UNIT_RETAINED', unit=unit_id, cause=cause)
        for process in list(self._descendants):
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                pass
        self._descendants.clear()
        self._event('CANCELLED', retained=retained)
        self._close_locks()
        self._released = True
        return {'retained': retained}

    def release_locks(self):
        """Libera los locks sin cambiar estado (mismo efecto que la muerte del
        proceso: el SO libera los flock al cerrar los descriptores). No marca
        unidades ni toca el presupuesto; permite simular caídas y entregar la
        misión a otro controlador sin cancelación."""
        self._close_locks()
        self._released = True

    # -- internos ----------------------------------------------------------

    def _ensure_active(self):
        if self._released:
            raise HostError('Controlador liberado: locks cerrados')

    def _unit_view(self, unit):
        return dict(unit)

    def _check_received(self, unit):
        task_bytes = Path(unit['task_ref']).read_bytes()
        if missions.digest(task_bytes) != unit['task_sha256']:
            raise ValueError('sha256 de task no coincide con lo esperado')
        result_bytes = Path(unit['result_ref']).read_bytes()
        if missions.digest(result_bytes) != unit['result_sha256']:
            raise ValueError('sha256 de result no coincide con lo esperado')

    def _publish(self, unit):
        """Lote del publicador en almacén por unidad; idempotente por contenido."""
        store = Publisher(self._published_root / unit['unit_id'])
        batch_id = 'batch-' + unit['unit_id']
        try:
            store.resolve(batch_id + '-close')
            return batch_id  # ya publicado con el contenido determinista de la unidad
        except ValueError:
            pass
        identity = self._mandate['identity']
        authorization = self._mandate['authorization']
        objective = unit.get('objective') or ('unidad ' + unit['unit_id'])
        store.open_batch(identity, authorization, objective, batch_id)
        evidence = store.publish_batch_record(
            identity, authorization, batch_id, 'evidence',
            {'task_ref': unit['task_ref'], 'task_sha256': unit['task_sha256'],
             'result_ref': unit['result_ref'], 'result_sha256': unit['result_sha256']},
            'evidence')['record_id']
        task = store.publish_batch_record(
            identity, authorization, batch_id, 'task',
            {'evidence_id': evidence}, 'task')['record_id']
        store.close_batch(identity, authorization, batch_id, 'COMPLETE', [evidence, task], [])
        return batch_id

    def _retain(self, unit, cause):
        cause = cause[:MAX_CAUSE]
        try:
            unit['state'] = 'RETAINED'
            unit['retained_cause'] = cause
            self._save_queue()
            self._event('UNIT_RETAINED', unit=unit['unit_id'], cause=cause)
        finally:
            self._unlock_unit(unit['unit_id'])
        return {'unit_id': unit['unit_id'], 'outcome': 'UNIT_RETAINED', 'cause': cause}

    def _lock_unit(self, unit_id):
        fd = os.open(self.locks_dir / (unit_id + '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise HostError('Lock de unidad ocupado: ' + unit_id)
        self._unit_fds[unit_id] = fd

    def _unlock_unit(self, unit_id):
        fd = self._unit_fds.pop(unit_id, None)
        if fd is not None:
            os.close(fd)  # cerrar el descriptor libera el flock

    def _close_locks(self):
        for unit_id in list(self._unit_fds):
            self._unlock_unit(unit_id)
        if getattr(self, '_controller_fd', None) is not None:
            os.close(self._controller_fd)
            self._controller_fd = None
        events = getattr(self, '_events', None)
        if events is not None:
            try:
                events.flush()
            except OSError:
                pass
            events.close()
            self._events = None

    def _load_mandate(self):
        if not self._mission_path.exists():
            return None
        mission = missions.read_json(self._mission_path)
        if mission.get('version') != 1 or mission.get('kind') != 'host-mission':
            raise ValueError('Mandato persistido inválido')
        for field in ('identity', 'authorization'):
            value = mission.get(field)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError('Mandato persistido inválido: ' + field)
        return {'identity': mission['identity'], 'authorization': mission['authorization'],
                'limits': _check_limits(mission.get('limits'))}

    def _load_queue(self):
        if not self._queue_path.exists():
            return {'version': 1, 'kind': 'host-queue', 'units': []}
        raw = missions.read_json(self._queue_path)
        if raw.get('version') != 1 or raw.get('kind') != 'host-queue' or not isinstance(raw.get('units'), list):
            raise ValueError('Cola persistida inválida')
        for unit in raw['units']:
            _validate_unit(unit)
        identifiers = [unit['unit_id'] for unit in raw['units']]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError('Cola persistida con unidades duplicadas')
        return raw

    def _save_queue(self):
        raw = json.dumps(self._queue, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
        with tempfile.NamedTemporaryFile(dir=self.mission_dir, prefix='.queue-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, self._queue_path)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        self._fsync_dir()

    def _fsync_dir(self):
        try:
            fd = os.open(self.mission_dir, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def _count_events(self):
        if not self._events_path.exists():
            return 0
        with self._events_path.open('rb') as stream:
            return sum(1 for _ in stream)

    def _event(self, name, **fields):
        self._seq += 1
        record = {'version': 1, 'seq': self._seq, 'ts': round(time.time(), 6), 'event': name, **fields}
        self._events.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + '\n')
        self._events.flush()
        os.fsync(self._events.fileno())

    def __del__(self):
        try:
            self._close_locks()
        except Exception:
            pass
