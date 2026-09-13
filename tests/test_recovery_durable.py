"""Recuperación durable y operación continua sobre fixtures; sin modelos, sin misión real.

python3 -B -m unittest discover -s tests -p test_recovery_durable.py -v

Nivel de evidencia por mecanismo:
- Framework: idempotencia/exclusión del publicador, `missions.run_check` mata el
  grupo de proceso al agotar el turno, `host_launcher` termina los descendientes
  del sandbox por namespace de PID y conserva el estado externo host-side entre
  lanzamientos, `budget.Ledger` persiste el gasto y no lo reinicia.
- Arnés fixture: el controlador de sesión demuestra el contrato de reconciliación
  (reanudar desde estado externo, sin reenvíos ciegos) que deberá satisfacer el
  Host. No es el Host ni acredita autonomía LLM ni descendientes remotos.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import missions
from budget import BudgetExhausted, Ledger
from host_launcher import launch
from publisher import Publisher

PYTHON = shutil.which('python3')
SLEEP = shutil.which('sleep')
TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parents[0] / 'scripts'
BWRAP = Path('/usr/bin/bwrap')
DEFAULT_LIMITS = {'attempts': 6, 'cost': 40, 'seconds': 30}


class Crash(BaseException):
    """Muerte simulada del controlador en un punto de transición; run() no la captura."""


def _crash_at(point):
    def inject(name):
        if name == point:
            raise Crash(point)
    return inject


def _save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    missions.save(path, value)


class FixtureSession:
    """Controlador fixture: consume una cola externa con presupuesto duradero.

    Estado externo: recibos por unidad, ledger de presupuesto, artefactos de
    misión y marcadores RETAINED. `auditor ACCEPTED` define unidad DONE. Toda
    reanudación reconstruye desde ese estado; ninguna escritura se reenvía a
    ciegas (el publicador rechaza contenido distinto para el mismo registro).
    """

    def __init__(self, root, units, *, inject=None, limits=None):
        self.root = Path(root)
        self.units = units
        self.inject = inject or (lambda name: None)
        self.budget = Ledger(self.root / 'budget', **(limits or DEFAULT_LIMITS))
        self._publishers = {}

    def publisher(self, unit):
        if unit not in self._publishers:
            self._publishers[unit] = Publisher(self.root / 'receipts' / unit)
        return self._publishers[unit]

    def batch_id(self, unit):
        return 'batch-' + unit

    def done(self, unit):
        return (self.root / 'receipts' / unit / (self.batch_id(unit) + '-auditor.json')).exists()

    def retained(self, unit):
        return (self.root / 'retained' / (unit + '.json')).exists()

    def pending(self):
        return [unit for unit in sorted(self.units) if not self.done(unit) and not self.retained(unit)]

    def run(self, units=None):
        summary = {'done': [], 'retained': []}
        for unit in (self.pending() if units is None else
                     [u for u in units if not self.done(u) and not self.retained(u)]):
            spec = self.units[unit]
            self.budget.reserve(attempts=1, cost=spec['cost'], seconds=spec['seconds'])
            self._process(unit)
            summary['retained' if self.retained(unit) else 'done'].append(unit)
        return summary

    def _process(self, unit):
        spec = self.units[unit]
        candidate = self.root / 'candidates' / unit
        task_path = self.root / 'tasks' / (unit + '.json')
        files = sorted(spec['files'])
        if not task_path.exists():
            _save(task_path, dict(
                version=1, mode='repair', objective=spec['objective'],
                authorization_ref='fixture only', executor=unit + '-executor',
                criteria=[spec['objective']], root=str(candidate), files=files,
                change_scope=spec['change_scope'], commands=[spec['argv']],
                timeout_seconds=spec['timeout_seconds'],
                base=missions.snapshot(self.root / 'products' / unit, files)))
        if not candidate.exists():
            shutil.copytree(self.root / 'products' / unit, candidate)
        red, _ = self._check(unit, 'red', task_path, spec, candidate, files)
        if red['exit_code'] == 0 and not red['timed_out']:
            raise ValueError('Fixture sin reproducción roja: ' + unit)
        self._apply_fix(unit, spec, candidate)
        green, green_dir = self._check(unit, 'green', task_path, spec, candidate, files)
        if green['timed_out']:
            self._retain(unit, 'timeout de turno del fixture')
            return
        if green['exit_code'] != 0:
            self._retain(unit, 'prueba verde fallida en fixture')
            return
        qa_path = self.root / 'qa' / (unit + '.json')
        if not qa_path.exists():
            _save(qa_path, dict(
                task_sha256=missions.digest(task_path.read_bytes()), files=green['after'],
                check_sha256=missions.digest((green_dir / 'check.json').read_bytes()),
                reviewer=unit + '-qa', session_ref='fixture-only',
                review='QA simulada del fixture; no es revisión de agente.', verdict='ACCEPTED'))
        self.inject('during_qa')
        result_path = self.root / 'results' / (unit + '.json')
        if not result_path.exists():
            findings = self.root / 'findings' / (unit + '.txt')
            if not findings.exists():
                findings.parent.mkdir(parents=True, exist_ok=True)
                findings.write_text('Fixture ' + unit + ': eliminar el desfase; prueba verde.')
            _save(result_path, dict(
                version=1, task_sha256=missions.digest(task_path.read_bytes()),
                files=green['after'], status='ACCEPTED', findings_ref=str(findings),
                findings_sha256=missions.digest(findings.read_bytes()),
                check_ref=str(green_dir / 'check.json'), qa_ref=str(qa_path),
                qa_sha256=missions.digest(qa_path.read_bytes())))
        if not missions.verify(task_path, result_path).startswith('ACCEPTED'):
            self._retain(unit, 'verificación documental no aceptada')
            return
        self.inject('before_publish')
        store = self.publisher(unit)
        batch = self.batch_id(unit)
        evidence_payload = {
            'task_ref': str(task_path), 'task_sha256': missions.digest(task_path.read_bytes()),
            'result_ref': str(result_path), 'result_sha256': missions.digest(result_path.read_bytes())}
        try:
            closed = store.resolve(batch + '-close')
        except ValueError:
            closed = None
        if closed is None:
            # Los registros de lote solo se publican sin cierre; con cierre, el
            # contenido ya está integrado y las etapas se reanudan idempotentes.
            store.open_batch('owner-fixture', 'auth-fixture', spec['objective'], batch)
            evidence = store.publish_batch_record(
                'owner-fixture', 'auth-fixture', batch, 'evidence',
                evidence_payload, 'evidence')['record_id']
            task = store.publish_batch_record(
                'owner-fixture', 'auth-fixture', batch, 'task',
                {'evidence_id': evidence}, 'task')['record_id']
            closed = store.close_batch('owner-fixture', 'auth-fixture', batch, 'COMPLETE',
                                       [evidence, task], [])
        else:
            evidence = batch + '-evidence'
        store.report_stage('owner-fixture', 'auth-fixture', batch, 'executor', 'CANDIDATE',
                           evidence, unit + '-executor')
        self.inject('after_publish')
        store.report_stage('owner-fixture', 'auth-fixture', batch, 'qa', 'VERIFIED',
                           evidence, unit + '-qa')
        store.report_stage('owner-fixture', 'auth-fixture', batch, 'auditor', 'ACCEPTED',
                           evidence, unit + '-auditor')

    def _check(self, unit, role, task_path, spec, candidate, files):
        timeout = spec.get('check_timeout', spec['timeout_seconds'])
        index = 0
        while True:
            out = self.root / 'runs' / (unit + '-' + role + ('' if index == 0 else '-' + str(index + 1)))
            if not out.exists():
                out.parent.mkdir(parents=True, exist_ok=True)
                return missions.run_check(task_path, out, spec['argv'], timeout), out
            check = out / 'check.json'
            if check.exists():
                record = json.loads(check.read_text())
                if role == 'red' or (not record['timed_out'] and record['exit_code'] == 0
                                     and record['after'] == missions.snapshot(candidate, files)):
                    return record, out
            index += 1

    def _apply_fix(self, unit, spec, candidate):
        for name, content in spec.get('fix', {}).items():
            path = candidate / name
            original = (self.root / 'products' / unit / name).read_bytes()
            if path.read_bytes() == original:  # idempotente: no pisa ajustes posteriores
                path.write_text(content)

    def _retain(self, unit, reason):
        path = self.root / 'retained' / (unit + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            _save(path, {'unit': unit, 'reason': reason})


SLEEPER_BUGGY = '''import fcntl, subprocess, sys, time
handle = open(sys.argv[1], 'w')
fcntl.flock(handle, fcntl.LOCK_EX)
child = subprocess.Popen([sys.argv[2], '300'])
print(child.pid, flush=True)
time.sleep(300)
'''
SLEEPER_PARTIAL = '''import fcntl, subprocess, sys, time
handle = open(sys.argv[1], 'w')
fcntl.flock(handle, fcntl.LOCK_EX)
child = subprocess.Popen([sys.argv[2], '300'])
print(child.pid, flush=True)
time.sleep(5)
'''
SLEEPER_FIXED = 'print("contract passed")\n'

FIXED_CANDIDATE = {'calc.py': b'def total(items): return len(items)\n',
                   'test_calc.py': b'from calc import total\nassert total([]) == 0\nprint("contract passed")\n'}

FLOCK_SLEEP = '''import fcntl, sys, time
handle = open(sys.argv[1], 'w')
fcntl.flock(handle, fcntl.LOCK_EX)
print('locked', flush=True)
time.sleep(300)
'''

WORKER = r'''
import json, os, signal, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import test_recovery_durable as t
root, mode = t.Path(sys.argv[2]), sys.argv[3]
state = root / 'worker-state'
state.mkdir(parents=True, exist_ok=True)
if mode == 'CANCELLATION':
    tracked = []
    def cancel(signum, frame):
        for pgid in tracked:
            os.killpg(pgid, signal.SIGKILL)
        os.killpg(os.getpgid(0), signal.SIGKILL)
    signal.signal(signal.SIGTERM, cancel)
    specs = json.loads(sys.argv[4])
    session = t.FixtureSession(root, specs)
    unit = session.pending()[0]
    session.budget.reserve(attempts=1, cost=specs[unit]['cost'], seconds=specs[unit]['seconds'])
    lock = root / 'locks' / 'cancel.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    turn = subprocess.Popen([t.PYTHON, '-B', str(root / 'flock-sleep.py'), str(lock)],
                            start_new_session=True)
    tracked.append(turn.pid)
    turn.wait()
    raise SystemExit(0)
def wait(name):
    marker = state / ('wait-' + name)
    marker.write_text('waiting')
    deadline = time.monotonic() + 90
    while not (state / ('continue-' + name)).exists():
        if time.monotonic() > deadline:
            raise SystemExit(3)
        time.sleep(0.05)
    marker.unlink()
session = t.FixtureSession(root, json.loads(sys.argv[4]),
                           inject=lambda name: wait(name) if name == mode else None)
session.run()
'''

LAUNCH_WORKER = r'''
import hashlib, json, os, sys, time
assert not os.path.exists(sys.argv[1]), 'receipts visible inside sandbox'
try:
    open(os.path.join(sys.argv[2], 'escape'), 'w')
    raise SystemExit(5)
except OSError:
    pass
mode, calc = sys.argv[3], sys.argv[4]
digest = hashlib.sha256(open(calc, 'rb').read()).hexdigest()
if mode in ('wait_early', 'wait_ack'):
    time.sleep(120)
if mode == 'ack':
    with open('/state/ack.json', 'w') as stream:
        json.dump({'calc_sha256': digest}, stream)
    print('ACK DONE', flush=True)
    raise SystemExit(0)
with open('/state/qa.json', 'w') as stream:
    json.dump({'task_sha256': sys.argv[5], 'check_sha256': sys.argv[6], 'calc_sha256': digest}, stream)
if mode == 'wait_late':
    print('WAITING', flush=True)
    time.sleep(120)
print('QA TURN DONE', flush=True)
'''


class RecoveryDurableTest(unittest.TestCase):
    maxDiff = None

    def _root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _specs(self, root, units):
        specs = {}
        for unit in units:
            product = root / 'products' / unit
            product.mkdir(parents=True)
            (product / 'calc.py').write_text('def total(items): return len(items) + 1\n')
            (product / 'test_calc.py').write_text(
                'from calc import total\nassert total([]) == 0\nprint("contract passed")\n')
            specs[unit] = dict(
                unit=unit, objective='total vacio es cero ' + unit,
                files=['calc.py', 'test_calc.py'], change_scope=['calc.py'],
                argv=[PYTHON, '-B', 'test_calc.py'], timeout_seconds=10,
                cost=10, seconds=5, fix={'calc.py': 'def total(items): return len(items)\n'})
        return specs

    def _sleeper_specs(self, root, unit='t1'):
        product = root / 'products' / unit
        product.mkdir(parents=True)
        lock = root / 'locks' / (unit + '.lock')
        lock.parent.mkdir(parents=True, exist_ok=True)
        (product / 'work.py').write_text(SLEEPER_BUGGY)
        return {unit: dict(
            unit=unit, objective='turno acotado ' + unit, files=['work.py'],
            change_scope=['work.py'], timeout_seconds=10, check_timeout=2,
            argv=[PYTHON, '-B', 'work.py', str(lock), SLEEP],
            cost=10, seconds=5, fix={'work.py': SLEEPER_PARTIAL})}, lock

    def _tree(self, directory):
        return {str(path.relative_to(directory)): path.read_bytes()
                for path in sorted(Path(directory).rglob('*')) if path.is_file()}

    def _wait_lock_free(self, lock, deadline=5.0):
        import fcntl
        limit = time.monotonic() + deadline
        while time.monotonic() < limit:
            try:
                handle = os.open(lock, os.O_RDWR)
            except OSError:
                return False
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.close(handle)
                return True
            except OSError:
                os.close(handle)
                time.sleep(0.05)
        return False

    def _wait_gone(self, pid, deadline=5.0):
        limit = time.monotonic() + deadline
        while time.monotonic() < limit:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.05)
        return False

    def _stage(self, session, unit, stage):
        try:
            return session.publisher(unit).resolve(session.batch_id(unit) + '-' + stage)['payload']['status']
        except ValueError:
            return None

    def _has_records(self, root, unit):
        receipts = Path(root) / 'receipts' / unit
        return receipts.exists() and any(receipts.glob('*.json'))

    # 1. Operación normal continuada: 4 unidades de la cola en una sola sesión,
    # con presupuesto persistente, sin intervención; agotamiento fail-closed.
    def test_continuous_operation_within_persistent_budget(self):
        root = self._root()
        units = ('u1', 'u2', 'u3', 'u4')
        specs = self._specs(root, units)
        session = FixtureSession(root, specs)
        self.assertEqual(session.budget.limits, DEFAULT_LIMITS)
        self.assertEqual(session.run(), {'done': sorted(units), 'retained': []})
        self.assertEqual(session.pending(), [])
        self.assertEqual(session.budget.usage(), {'attempts': 4, 'cost': 40, 'seconds': 20})
        for unit in units:
            self.assertEqual(self._stage(session, unit, 'executor'), 'CANDIDATE')
            self.assertEqual(self._stage(session, unit, 'qa'), 'VERIFIED')
            self.assertEqual(self._stage(session, unit, 'auditor'), 'ACCEPTED')
            store = session.publisher(unit)
            closed = store.resolve(session.batch_id(unit) + '-close')
            self.assertEqual(closed['payload']['status'], 'COMPLETE')
            self.assertEqual(store.resolve_handoff(store.handoff(closed['record_id'])), closed)
            self.assertEqual(len(list((root / 'receipts' / unit).glob('*.json'))), 7)
            self.assertTrue(missions.verify(root / 'tasks' / (unit + '.json'),
                                            root / 'results' / (unit + '.json')).startswith('ACCEPTED'))
        # Segunda pasada sin trabajo nuevo: cero integración repetida, bytes iguales.
        before = self._tree(root / 'receipts')
        self.assertEqual(session.run(), {'done': [], 'retained': []})
        self.assertEqual(self._tree(root / 'receipts'), before)
        # Reapertura: el gasto persiste y no se reinicia; límites distintos fallan.
        reopened = Ledger(root / 'budget')
        self.assertEqual(reopened.usage(), {'attempts': 4, 'cost': 40, 'seconds': 20})
        with self.assertRaises(ValueError):
            Ledger(root / 'budget', attempts=3, cost=40, seconds=30)
        # Nueva unidad sin presupuesto restante: fail-closed, sin escrituras.
        specs.update(self._specs(root, ('u5',)))
        usage_before = self._tree(root / 'budget')
        with self.assertRaises(BudgetExhausted):
            session.run(['u5'])
        self.assertEqual(session.budget.usage(), {'attempts': 4, 'cost': 40, 'seconds': 20})
        self.assertEqual(self._tree(root / 'budget'), usage_before)
        self.assertFalse(self._has_records(root, 'u5'))
        self.assertIn('u5', session.pending())

    # Presupuesto durable: eventos exclusivos e inmutables, límites inmutables,
    # alteración detectada, reserva conservadora antes del trabajo.
    def test_budget_ledger_durability(self):
        root = self._root()
        ledger = Ledger(root / 'budget', attempts=3, cost=100, seconds=60)
        first = ledger.reserve(attempts=1, cost=40, seconds=10)
        self.assertEqual(first['usage'], {'attempts': 1, 'cost': 40, 'seconds': 10})
        with self.assertRaises(BudgetExhausted):
            ledger.reserve(cost=61)
        self.assertEqual(len(list((root / 'budget').glob('e-*.json'))), 1)
        for kwargs in ({'attempts': -1}, {'cost': True}, {'seconds': '1'}, {'attempts': 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ledger.reserve(**kwargs)
        reopened = Ledger(root / 'budget')
        self.assertEqual(reopened.usage(), first['usage'])
        self.assertEqual(reopened.limits, {'attempts': 3, 'cost': 100, 'seconds': 60})
        reopened.reserve(seconds=50)
        with self.assertRaises(BudgetExhausted):
            reopened.reserve(seconds=1)
        event = next(path for path in (root / 'budget').glob('e-*.json')
                     if '"cost": 40' in path.read_text())
        event.write_text(event.read_text().replace('"cost": 40', '"cost": 4'))
        with self.assertRaises(ValueError):
            reopened.usage()
        event.write_bytes(b'{"version": 1}')
        with self.assertRaises(ValueError):
            reopened.usage()
        limits = root / 'budget' / 'limits.json'
        limits.write_text(limits.read_text().replace('"attempts": 3', '"attempts": 9'))
        with self.assertRaises(ValueError):
            Ledger(root / 'budget')

    # 2. Fallos en puntos de transición con reinicio del controlador:
    # reconciliación idempotente, cero escritores duplicados, cero integración
    # repetida, candidato conservado, presupuesto no reiniciado.
    def test_controller_restart_at_transition_points(self):
        for point in ('during_qa', 'before_publish', 'after_publish'):
            with self.subTest(point=point):
                root = self._root()
                specs = self._specs(root, ('x',))
                crashed = FixtureSession(root, specs, inject=_crash_at(point))
                with self.assertRaises(Crash):
                    crashed.run(['x'])
                candidate = root / 'candidates' / 'x'
                self.assertEqual({name: (candidate / name).read_bytes() for name in FIXED_CANDIDATE},
                                 FIXED_CANDIDATE)
                if point == 'during_qa':
                    self.assertFalse(self._has_records(root, 'x'))
                    self.assertTrue((root / 'qa' / 'x.json').exists())
                elif point == 'before_publish':
                    self.assertFalse(self._has_records(root, 'x'))
                    self.assertTrue(missions.verify(root / 'tasks' / 'x.json',
                                                    root / 'results' / 'x.json').startswith('ACCEPTED'))
                else:
                    self.assertEqual(self._stage(crashed, 'x', 'executor'), 'CANDIDATE')
                    self.assertIsNone(self._stage(crashed, 'x', 'qa'))
                self.assertEqual(crashed.budget.usage(), {'attempts': 1, 'cost': 10, 'seconds': 5})
                # Reinicio: controlador nuevo desde estado externo; completa sin reenvío ciego.
                session = FixtureSession(root, specs)
                self.assertEqual(session.run(['x']), {'done': ['x'], 'retained': []})
                self.assertEqual(self._stage(session, 'x', 'executor'), 'CANDIDATE')
                self.assertEqual(self._stage(session, 'x', 'qa'), 'VERIFIED')
                self.assertEqual(self._stage(session, 'x', 'auditor'), 'ACCEPTED')
                receipts = root / 'receipts' / 'x'
                self.assertEqual(len(list(receipts.glob('*.json'))), 7)
                self.assertEqual(session.budget.usage(), {'attempts': 2, 'cost': 20, 'seconds': 10})
                self.assertEqual({name: (candidate / name).read_bytes() for name in FIXED_CANDIDATE},
                                 FIXED_CANDIDATE)
                store = session.publisher('x')
                batch = 'batch-x'
                closed = store.resolve(batch + '-close')
                self.assertEqual(store.resolve_handoff(store.handoff(closed['record_id'])), closed)
                # Idempotencia exacta: reabrir el lote cerrado devuelve el mismo recibo
                # (los registros de lote tras el cierre se rechazan por contrato).
                evidence = store.resolve(batch + '-evidence')
                self.assertEqual(store.open_batch('owner-fixture', 'auth-fixture',
                                                  specs['x']['objective'], batch)['receipt'],
                                 store.resolve(batch + '-open'))
                # Ningún reenvío ciego: contenido distinto al mismo registro se rechaza sin escribir.
                before = self._tree(receipts)
                with self.assertRaises(ValueError):
                    store.publish('owner-fixture', 'auth-fixture', {'changed': True}, batch + '-evidence')
                with self.assertRaises(ValueError):
                    store.report_stage('owner-fixture', 'auth-fixture', batch, 'executor', 'FAILED',
                                       batch + '-evidence', 'x-executor')
                with self.assertRaises(ValueError):
                    store.close_batch('owner-fixture', 'auth-fixture', batch, 'PARTIAL',
                                      [batch + '-evidence', batch + '-task'], ['no'])
                with self.assertRaises(ValueError):
                    store.report_stage('owner-fixture', 'auth-fixture', batch, 'auditor', 'RETAINED',
                                       batch + '-evidence', 'x-auditor')
                self.assertEqual(self._tree(receipts), before)
                # Escritor externo: mismo contenido idempotente, contenido distinto en conflicto.
                probe = ('import json, sys\n'
                         'sys.path.insert(0, sys.argv[1])\n'
                         'from publisher import Publisher\n'
                         'store = Publisher(sys.argv[2])\n'
                         'try:\n'
                         '    store.publish(sys.argv[3], sys.argv[4], json.loads(sys.argv[6]), sys.argv[5])\n'
                         '    print("IDEMPOTENT")\n'
                         'except ValueError:\n'
                         '    print("CONFLICT")\n')
                for payload, expected in ((evidence['payload'], 'IDEMPOTENT'),
                                          ({'other': 1}, 'CONFLICT')):
                    process = subprocess.run(
                        [PYTHON, '-B', '-c', probe, str(SCRIPTS_DIR), str(receipts),
                         'owner-fixture', 'auth-fixture', batch + '-evidence', json.dumps(payload)],
                        capture_output=True, text=True)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(process.stdout.strip(), expected)

    # 3. Caída de worker (SIGKILL) en punto de transición: estado externo
    # intacto, restos de escritura inofensivos, reanudación completa.
    def test_worker_drop_at_checkpoint(self):
        root = self._root()
        specs = self._specs(root, ('w',))
        worker = subprocess.Popen(
            [PYTHON, '-B', '-c', WORKER, str(TESTS_DIR), str(root), 'after_publish', json.dumps(specs)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        marker = root / 'worker-state' / 'wait-after_publish'
        limit = time.monotonic() + 30
        while not marker.exists():
            self.assertLess(time.monotonic(), limit, 'worker no alcanzó el punto: ' + str(worker.poll()))
            time.sleep(0.05)
        worker.kill()
        worker.wait(timeout=10)
        for stream in (worker.stdout, worker.stderr):
            stream.close()
        session = FixtureSession(root, specs)
        self.assertEqual(self._stage(session, 'w', 'executor'), 'CANDIDATE')
        self.assertEqual(session.run(['w']), {'done': ['w'], 'retained': []})
        self.assertEqual(session.budget.usage(), {'attempts': 2, 'cost': 20, 'seconds': 10})
        receipts = root / 'receipts' / 'w'
        self.assertEqual(len(list(receipts.glob('*.json'))), 7)
        # Restos de un corte durante escritura (temporal huérfano): inofensivos.
        orphan = receipts / '.receipt-orphan'
        orphan.write_text('corte a mitad de escritura')
        store = session.publisher('w')
        closed = store.resolve('batch-w-close')
        self.assertEqual(store.resolve_handoff(store.handoff(closed['record_id'])), closed)
        store.publish('owner-fixture', 'auth-fixture', {}, 'after-orphan')
        self.assertTrue(orphan.exists())

    # 4. Cancelación del controlador fixture: los descendientes locales mueren
    # (evidencia por flock), el estado queda recuperable y el presupuesto no se
    # reinicia. Los descendientes remotos quedan fuera de la capacidad aceptada
    # y se documentan como límite.
    def test_cancellation_terminates_local_descendants(self):
        root = self._root()
        specs = self._specs(root, ('c',))
        (root / 'flock-sleep.py').write_text(FLOCK_SLEEP)
        worker = subprocess.Popen(
            [PYTHON, '-B', '-c', WORKER, str(TESTS_DIR), str(root), 'CANCELLATION', json.dumps(specs)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        lock = root / 'locks' / 'cancel.lock'
        limit = time.monotonic() + 30
        while not lock.exists():
            self.assertLess(time.monotonic(), limit, 'worker no arrancó: ' + str(worker.poll()))
            time.sleep(0.05)
        self.assertTrue(worker.stdout.readline().startswith(b'locked'))
        worker.send_signal(signal.SIGTERM)
        worker.wait(timeout=10)
        for stream in (worker.stdout, worker.stderr):
            stream.close()
        self.assertTrue(self._wait_lock_free(lock), 'descendiente local sobrevivió a la cancelación')
        self.assertIsNone(self._stage(FixtureSession(root, specs), 'c', 'executor'))
        self.assertFalse((root / 'retained' / 'c.json').exists())
        self.assertEqual(FixtureSession(root, specs).budget.usage(),
                         {'attempts': 1, 'cost': 10, 'seconds': 5})
        session = FixtureSession(root, specs)
        self.assertEqual(session.run(['c']), {'done': ['c'], 'retained': []})
        self.assertEqual(session.budget.usage(), {'attempts': 2, 'cost': 20, 'seconds': 10})
        self.assertEqual(self._stage(session, 'c', 'auditor'), 'ACCEPTED')

    # 5. Timeout de turno: run_check mata el grupo del comando (framework),
    # la unidad queda RETAINED y preservada, y es recuperable más adelante.
    def test_turn_timeout_retains_and_recovers(self):
        root = self._root()
        specs, lock = self._sleeper_specs(root)
        session = FixtureSession(root, specs)
        self.assertEqual(session.run(['t1']), {'done': [], 'retained': ['t1']})
        self.assertIsNone(self._stage(session, 't1', 'executor'))
        self.assertTrue(self._wait_lock_free(lock), 'descendiente del turno sobrevivió al timeout')
        stdout = (root / 'runs' / 't1-green' / 'stdout.txt').read_text().strip()
        self.assertTrue(stdout.isdigit(), stdout)
        self.assertTrue(self._wait_gone(int(stdout)), 'descendiente duplicado sigue en /proc')
        self.assertFalse(self._has_records(root, 't1'))
        candidate = root / 'candidates' / 't1' / 'work.py'
        self.assertEqual(candidate.read_text(), SLEEPER_PARTIAL)
        self.assertEqual(session.budget.usage(), {'attempts': 1, 'cost': 10, 'seconds': 5})
        # Recuperación: decisión externa corrige el candidato y retira la retención.
        candidate.write_text(SLEEPER_FIXED)
        (root / 'retained' / 't1.json').unlink()
        session = FixtureSession(root, specs)
        self.assertEqual(session.run(['t1']), {'done': ['t1'], 'retained': []})
        self.assertEqual(self._stage(session, 't1', 'executor'), 'CANDIDATE')
        self.assertEqual(self._stage(session, 't1', 'qa'), 'VERIFIED')
        self.assertEqual(self._stage(session, 't1', 'auditor'), 'ACCEPTED')
        self.assertEqual(session.budget.usage(), {'attempts': 2, 'cost': 20, 'seconds': 10})
        store = session.publisher('t1')
        self.assertEqual(store.resolve_handoff(store.handoff('batch-t1-close'))['payload']['status'],
                         'COMPLETE')
        self.assertTrue((root / 'products' / 't1' / 'work.py').read_text().startswith('import fcntl'))

    # 6. Reinicio del Host (host_launcher): turno aislado cortado en los tres
    # puntos; el estado host-side (recibos, presupuesto, candidato) no se
    # reinicia ni reenvía a ciegas; el sandbox no ve ni escribe lo no montado.
    def test_host_restart_preserves_state_and_budget(self):
        if not BWRAP.exists():
            self.skipTest('bubblewrap no disponible; sin fallback')
        for point in ('before_publish', 'during_qa', 'after_publish'):
            with self.subTest(point=point):
                root = self._root()
                specs = self._specs(root, ('h',))
                session = FixtureSession(root, specs, limits={'attempts': 1, 'cost': 100, 'seconds': 60})
                candidate = root / 'candidates' / 'h'
                task_path = root / 'tasks' / 'h.json'
                shutil.copytree(root / 'products' / 'h', candidate)
                files = sorted(specs['h']['files'])
                _save(task_path, dict(
                    version=1, mode='repair', objective=specs['h']['objective'],
                    authorization_ref='fixture only', executor='h-executor',
                    criteria=[specs['h']['objective']], root=str(candidate), files=files,
                    change_scope=['calc.py'], commands=[specs['h']['argv']], timeout_seconds=10,
                    base=missions.snapshot(root / 'products' / 'h', files)))
                (root / 'runs').mkdir(parents=True, exist_ok=True)
                red = missions.run_check(task_path, root / 'runs' / 'h-red', specs['h']['argv'], 10)
                self.assertNotEqual(red['exit_code'], 0)
                (candidate / 'calc.py').write_text('def total(items): return len(items)\n')
                green = missions.run_check(task_path, root / 'runs' / 'h-green', specs['h']['argv'], 10)
                green_dir = root / 'runs' / 'h-green'
                self.assertEqual(green['exit_code'], 0)
                session.budget.reserve(attempts=1, cost=10, seconds=20)
                usage = {'attempts': 1, 'cost': 10, 'seconds': 20}
                worker_path = root / 'launch-worker.py'
                worker_path.write_text(LAUNCH_WORKER)
                (root / 'launch-state').mkdir()
                task_sha = missions.digest(task_path.read_bytes())
                check_sha = missions.digest((green_dir / 'check.json').read_bytes())
                calc_sha = missions.digest((candidate / 'calc.py').read_bytes())

                def launch_worker(mode, timeout=30):
                    return launch(reads={'product': candidate, 'worker': worker_path},
                                  state_parent=root / 'launch-state', cwd=candidate, timeout=timeout,
                                  argv=['/usr/bin/python3', '-B', '/inputs/worker', str(root / 'receipts'),
                                        str(candidate), mode, str(candidate / 'calc.py'), task_sha, check_sha])

                first_state, code = launch_worker(
                    'wait_early' if point == 'before_publish' else
                    ('wait_late' if point == 'during_qa' else 'full'),
                    timeout=2.5 if point != 'after_publish' else 30)
                if point == 'after_publish':
                    self.assertEqual(code, 0, (first_state / 'stderr.log').read_text())
                    self._collect_and_publish(root, session, first_state, task_sha, check_sha, green)
                else:
                    self.assertEqual(code, 124)
                    self.assertIn('FAIL CLOSED', (first_state / 'stderr.log').read_text())
                # El resultado de un turno muerto no se cobra ni se publica a ciegas.
                self.assertEqual(session.budget.usage(), usage)
                if point != 'after_publish':
                    self.assertFalse(self._has_records(root, 'h'))
                self.assertEqual({name: (candidate / name).read_bytes() for name in FIXED_CANDIDATE},
                                 FIXED_CANDIDATE)
                if point == 'before_publish':
                    self.assertFalse((first_state / 'qa.json').exists())
                    second_state, code = launch_worker('full')
                    self.assertEqual(code, 0, (second_state / 'stderr.log').read_text())
                    self.assertNotEqual(first_state, second_state)
                    self._collect_and_publish(root, session, second_state, task_sha, check_sha, green)
                    self._ack(session)
                elif point == 'during_qa':
                    # Artefacto producido en el turno muerto: queda sin recolectar y se repite el turno.
                    self.assertTrue((first_state / 'qa.json').exists())
                    second_state, code = launch_worker('full')
                    self.assertEqual(code, 0, (second_state / 'stderr.log').read_text())
                    self.assertNotEqual(first_state, second_state)
                    self._collect_and_publish(root, session, second_state, task_sha, check_sha, green)
                    self._ack(session)
                else:
                    killed_state, code = launch_worker('wait_ack', timeout=2.5)
                    self.assertEqual(code, 124)
                    self.assertIn('FAIL CLOSED', (killed_state / 'stderr.log').read_text())
                    self.assertFalse((killed_state / 'ack.json').exists())
                    self.assertIsNone(self._stage(session, 'h', 'qa'))
                    ack_state, code = launch_worker('ack')
                    self.assertEqual(code, 0, (ack_state / 'stderr.log').read_text())
                    ack = json.loads((ack_state / 'ack.json').read_text())
                    self.assertEqual(ack['calc_sha256'], calc_sha)
                    self._ack(session)
                self.assertEqual(self._stage(session, 'h', 'executor'), 'CANDIDATE')
                self.assertEqual(self._stage(session, 'h', 'qa'), 'VERIFIED')
                self.assertEqual(self._stage(session, 'h', 'auditor'), 'ACCEPTED')
                self.assertEqual(session.budget.usage(), usage)
                self.assertEqual(Ledger(root / 'budget').usage(), usage)
                with self.assertRaises(BudgetExhausted):
                    session.budget.reserve(attempts=1)
                closed = session.publisher('h').resolve('batch-h-close')
                self.assertEqual(session.publisher('h').resolve_handoff(
                    session.publisher('h').handoff(closed['record_id'])), closed)
                self.assertEqual(len(list((root / 'receipts' / 'h').glob('*.json'))), 7)
                # QA invalidada si cambia el candidato: hash desfasado, sin reenvío.
                (candidate / 'calc.py').write_text('def total(items): return 99\n')
                before = self._tree(root / 'receipts' / 'h')
                with self.assertRaises(ValueError):
                    session.publisher('h').report_stage('owner-fixture', 'auth-fixture', 'batch-h',
                                                        'auditor', 'RETAINED', 'batch-h-evidence', 'h-auditor')
                with self.assertRaises(ValueError):
                    missions.verify(task_path, root / 'results' / 'h.json')
                self.assertEqual(self._tree(root / 'receipts' / 'h'), before)

    def _ack(self, session):
        store = session.publisher('h')
        store.report_stage('owner-fixture', 'auth-fixture', 'batch-h',
                           'qa', 'VERIFIED', 'batch-h-evidence', 'h-qa')
        store.report_stage('owner-fixture', 'auth-fixture', 'batch-h',
                           'auditor', 'ACCEPTED', 'batch-h-evidence', 'h-auditor')

    def _collect_and_publish(self, root, session, state, task_sha, check_sha, green):
        produced = json.loads((state / 'qa.json').read_text())
        self.assertEqual(produced['calc_sha256'],
                         missions.digest((root / 'candidates' / 'h' / 'calc.py').read_bytes()))
        self.assertEqual(produced['task_sha256'], task_sha)
        self.assertEqual(produced['check_sha256'], check_sha)
        qa_path = root / 'qa' / 'h.json'
        if not qa_path.exists():
            _save(qa_path, dict(
                task_sha256=task_sha, files=green['after'], check_sha256=check_sha,
                reviewer='h-qa', session_ref='fixture-launch',
                review='QA de fixture producida en turno aislado; no es revisión semántica real.',
                verdict='ACCEPTED'))
        findings = root / 'findings' / 'h.txt'
        if not findings.exists():
            findings.parent.mkdir(parents=True, exist_ok=True)
            findings.write_text('Fixture h: eliminar el desfase; prueba verde en turno aislado.')
        result_path = root / 'results' / 'h.json'
        if not result_path.exists():
            _save(result_path, dict(
                version=1, task_sha256=task_sha, files=green['after'], status='ACCEPTED',
                findings_ref=str(findings), findings_sha256=missions.digest(findings.read_bytes()),
                check_ref=str(root / 'runs' / 'h-green' / 'check.json'), qa_ref=str(qa_path),
                qa_sha256=missions.digest(qa_path.read_bytes())))
        self.assertTrue(missions.verify(root / 'tasks' / 'h.json', result_path).startswith('ACCEPTED'))
        store = session.publisher('h')
        try:
            store.resolve('batch-h-close')
        except ValueError:
            store.open_batch('owner-fixture', 'auth-fixture', 'total vacio es cero h', 'batch-h')
            evidence = store.publish_batch_record(
                'owner-fixture', 'auth-fixture', 'batch-h', 'evidence',
                {'task_ref': str(root / 'tasks' / 'h.json'), 'task_sha256': task_sha,
                 'result_ref': str(result_path), 'result_sha256': missions.digest(result_path.read_bytes())},
                'evidence')['record_id']
            task = store.publish_batch_record(
                'owner-fixture', 'auth-fixture', 'batch-h', 'task',
                {'evidence_id': evidence}, 'task')['record_id']
            store.close_batch('owner-fixture', 'auth-fixture', 'batch-h', 'COMPLETE',
                              [evidence, task], [])
            store.report_stage('owner-fixture', 'auth-fixture', 'batch-h', 'executor', 'CANDIDATE',
                               evidence, 'h-executor')


if __name__ == '__main__':
    unittest.main()
