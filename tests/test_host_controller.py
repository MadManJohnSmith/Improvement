"""Controlador Host sobre fixtures: cola durable, presupuesto, reconciliación y cancelación.

python3 -B -m unittest tests.test_host_controller -v

Arnés fixture con turn_launcher determinista que graba recibos temporales y
devuelve dicts; sin red, sin modelos y sin procesos auxiliares. El contrato de
reconciliación sigue lo especificado en tests/test_recovery_durable.py; esto
no acredita autonomía LLM, aislamiento de turnos ni descendientes reales.
"""
import hashlib
import json
import sys
import tempfile
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget import BudgetExhausted, Ledger
from host_controller import ControllerAlive, HostController, HostError

LIMITS = {'attempts': 3, 'cost': 0, 'seconds': 0}


class Crash(BaseException):
    """Muerte simulada del controlador en un punto de transición; no se captura."""


def _crash_at(point):
    def inject(name):
        if name == point:
            raise Crash(point)
    return inject


class HostControllerTest(unittest.TestCase):
    maxDiff = None

    def _root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _sha(self, data):
        return hashlib.sha256(data).hexdigest()

    def _unit(self, root, unit_id):
        entry = {
            'unit_id': unit_id,
            'task_ref': str(root / 'artifacts' / unit_id / 'task.json'),
            'result_ref': str(root / 'artifacts' / unit_id / 'result.json'),
            'objective': 'unidad ' + unit_id,
        }
        plan = {'task': ('tarea ' + unit_id).encode(), 'result': ('resultado ' + unit_id).encode()}
        entry['task_sha256'] = self._sha(plan['task'])
        entry['result_sha256'] = self._sha(plan['result'])
        return entry, plan

    def _launcher(self, root, plans, calls):
        def launch(unit):
            unit_id = unit['unit_id']
            calls.append(unit_id)
            plan = plans[unit_id]
            task_path, result_path = Path(unit['task_ref']), Path(unit['result_ref'])
            task_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            if not task_path.exists():
                task_path.write_bytes(plan['task'])
            if not result_path.exists():
                result_path.write_bytes(plan['result'])
            receipt = root / 'receipts' / (unit_id + '.jsonl')
            receipt.parent.mkdir(parents=True, exist_ok=True)
            with receipt.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'unit': unit_id, 'turn': len(calls)}) + '\n')
            return {'unit_id': unit_id, 'turn': len(calls), 'receipt': str(receipt)}
        return launch

    def _events(self, mission_dir):
        return [(json.loads(line)['event'], json.loads(line).get('unit'))
                for line in (mission_dir / 'events.jsonl').read_text().splitlines()]

    def _queue(self, mission_dir):
        raw = json.loads((mission_dir / 'queue.json').read_text())
        return {unit['unit_id']: unit for unit in raw['units']}

    def _store_tree(self, mission_dir, unit_id):
        store = mission_dir / 'publish' / unit_id
        if not store.exists():
            return None
        return {path.name: path.read_bytes() for path in sorted(store.iterdir()) if path.is_file()}

    def _setup(self, root, unit_ids, limits=LIMITS):
        mission = root / 'mission'
        controller = HostController(mission)
        controller.register_mandate('host-fixture', limits)
        plans = {}
        for unit_id in unit_ids:
            entry, plan = self._unit(root, unit_id)
            plans[unit_id] = plan
            controller.enqueue(entry)
        return mission, controller, plans

    # 1. Consumo continuado: 3 unidades encoladas con presupuesto suficiente,
    # 3 UNIT_DONE, eventos en orden, sin intervención; segunda pasada sin escrituras.
    def test_continuous_consumption_of_three_units(self):
        root = self._root()
        mission, controller, plans = self._setup(root, ('u1', 'u2', 'u3'))
        calls = []
        launch = self._launcher(root, plans, calls)
        self.assertEqual(controller.run_all(launch), {'done': ['u1', 'u2', 'u3'], 'retained': []})
        self.assertEqual(calls, ['u1', 'u2', 'u3'])
        queue = self._queue(mission)
        self.assertEqual({unit_id: queue[unit_id]['state'] for unit_id in queue},
                         {'u1': 'DONE', 'u2': 'DONE', 'u3': 'DONE'})
        self.assertEqual(self._events(mission), [
            ('CONTROLLER_STARTED', None), ('MANDATE_REGISTERED', None),
            ('UNIT_ENQUEUED', 'u1'), ('UNIT_ENQUEUED', 'u2'), ('UNIT_ENQUEUED', 'u3'),
            ('TURN_STARTED', 'u1'), ('CHECK_RECEIVED', 'u1'), ('PUBLISHED', 'u1'), ('UNIT_DONE', 'u1'),
            ('TURN_STARTED', 'u2'), ('CHECK_RECEIVED', 'u2'), ('PUBLISHED', 'u2'), ('UNIT_DONE', 'u2'),
            ('TURN_STARTED', 'u3'), ('CHECK_RECEIVED', 'u3'), ('PUBLISHED', 'u3'), ('UNIT_DONE', 'u3')])
        self.assertEqual(controller.budget.usage(), {'attempts': 3, 'cost': 0, 'seconds': 0})
        for unit_id in ('u1', 'u2', 'u3'):
            tree = self._store_tree(mission, unit_id)
            self.assertEqual(sorted(tree), ['batch-%s-close.json' % unit_id,
                                            'batch-%s-evidence.json' % unit_id,
                                            'batch-%s-open.json' % unit_id,
                                            'batch-%s-task.json' % unit_id])
            entry, _ = self._unit(root, unit_id)
            evidence = json.loads(tree['batch-%s-evidence.json' % unit_id])
            self.assertEqual(evidence['payload']['payload'],
                             {'task_ref': entry['task_ref'], 'task_sha256': entry['task_sha256'],
                              'result_ref': entry['result_ref'], 'result_sha256': entry['result_sha256']})
            close = json.loads(tree['batch-%s-close.json' % unit_id])
            self.assertEqual(close['payload']['status'], 'COMPLETE')
        # Segunda pasada sin trabajo nuevo: cero escrituras (diario y almacén intactos).
        events_before = (mission / 'events.jsonl').read_bytes()
        stores_before = {unit_id: self._store_tree(mission, unit_id) for unit_id in ('u1', 'u2', 'u3')}
        self.assertEqual(controller.run_all(launch), {'done': [], 'retained': []})
        self.assertEqual((mission / 'events.jsonl').read_bytes(), events_before)
        self.assertEqual({unit_id: self._store_tree(mission, unit_id)
                          for unit_id in ('u1', 'u2', 'u3')}, stores_before)
        controller.release_locks()

    # 2. Presupuesto exacto para 2: la tercera falla cerrado (BudgetExhausted),
    # unidad PENDING sin escrituras; al reabrir el gasto 2/3 no se reinicia.
    def test_budget_exhaustion_fail_closed_and_persistent(self):
        root = self._root()
        mission, controller, plans = self._setup(
            root, ('a1', 'a2', 'a3'), limits={'attempts': 2, 'cost': 0, 'seconds': 0})
        calls = []
        launch = self._launcher(root, plans, calls)
        with self.assertRaises(BudgetExhausted):
            controller.run_all(launch)
        self.assertEqual(calls, ['a1', 'a2'])
        queue = self._queue(mission)
        self.assertEqual(queue['a1']['state'], 'DONE')
        self.assertEqual(queue['a2']['state'], 'DONE')
        self.assertEqual(queue['a3']['state'], 'PENDING')
        self.assertEqual(self._events(mission).count(('TURN_STARTED', 'a3')), 0)
        self.assertIsNone(self._store_tree(mission, 'a3'))
        self.assertFalse((mission / 'locks' / 'a3.lock').exists())
        usage = {'attempts': 2, 'cost': 0, 'seconds': 0}
        self.assertEqual(Ledger(mission / 'budget').usage(), usage)
        # Reapertura: gasto y límites conservados; nueva reserva falla cerrada.
        controller.release_locks()
        reopened = HostController(mission)
        self.assertEqual(reopened.budget.usage(), usage)
        self.assertEqual(reopened.budget.limits, {'attempts': 2, 'cost': 0, 'seconds': 0})
        with self.assertRaises(BudgetExhausted):
            reopened.budget.reserve(attempts=1)
        # Mandato reabierto: idéntico pasa sin escribir; distinto falla cerrado.
        self.assertEqual(reopened.register_mandate('host-fixture', {'attempts': 2, 'cost': 0, 'seconds': 0}),
                         {'created': False})
        with self.assertRaises(ValueError):
            reopened.register_mandate('host-fixture', {'attempts': 9, 'cost': 0, 'seconds': 0})
        with self.assertRaises(ValueError):
            reopened.register_mandate('otra-identidad', {'attempts': 2, 'cost': 0, 'seconds': 0})
        self.assertEqual(self._events(mission).count(('MANDATE_REGISTERED', None)), 1)
        reopened.release_locks()

    # 3. Caída simulada en cada transición: controlador nuevo sobre el mismo
    # mission_dir + reconcile_on_start reanuda sin duplicar escritor, sin
    # duplicar publicación (lotes idempotentes por contenido) y sin reiniciar
    # presupuesto; el relanzamiento del turno es responsabilidad del caller.
    def test_restart_at_each_transition_reconciles(self):
        for point in ('turn_started', 'check_received', 'published'):
            with self.subTest(point=point):
                root = self._root()
                mission, controller, plans = self._setup(root, ('x',))
                calls = []
                launch = self._launcher(root, plans, calls)
                with self.assertRaises(Crash):
                    controller.run_next(launch, inject=_crash_at(point))
                self.assertEqual(calls, [] if point == 'turn_started' else ['x'])
                self.assertEqual(self._queue(mission)['x']['state'], 'IN_FLIGHT')
                expected_last = {'turn_started': ('TURN_STARTED', 'x'),
                                 'check_received': ('CHECK_RECEIVED', 'x'),
                                 'published': ('PUBLISHED', 'x')}[point]
                self.assertEqual(self._events(mission)[-1], expected_last)
                self.assertEqual(Ledger(mission / 'budget').usage(),
                                 {'attempts': 1, 'cost': 0, 'seconds': 0})
                # Muerte simulada: liberar locks sin cambiar estado (como el SO).
                controller.release_locks()
                store_before = self._store_tree(mission, 'x')
                second = HostController(mission)
                self.assertEqual(second.reconcile_on_start(), {'reconciled': ['x']})
                self.assertEqual(self._queue(mission)['x']['state'], 'PENDING')
                # Idempotente: reconciliar de nuevo no escribe ni repite eventos.
                queue_bytes = (mission / 'queue.json').read_bytes()
                self.assertEqual(second.reconcile_on_start(), {'reconciled': []})
                self.assertEqual((mission / 'queue.json').read_bytes(), queue_bytes)
                self.assertEqual(self._events(mission).count(('UNIT_RECONCILED', 'x')), 1)
                self.assertEqual(second.run_all(launch), {'done': ['x'], 'retained': []})
                self.assertEqual(calls, ['x'] if point == 'turn_started' else ['x', 'x'])
                self.assertEqual(Ledger(mission / 'budget').usage(),
                                 {'attempts': 2, 'cost': 0, 'seconds': 0})
                self.assertEqual(second.budget.limits, LIMITS)
                tree = self._store_tree(mission, 'x')
                self.assertEqual(sorted(tree), ['batch-x-close.json', 'batch-x-evidence.json',
                                                'batch-x-open.json', 'batch-x-task.json'])
                if point == 'published':
                    self.assertEqual(tree, store_before)  # republicación idempotente
                else:
                    self.assertIsNone(store_before)
                self.assertEqual(json.loads(tree['batch-x-close.json'])['payload']['status'], 'COMPLETE')
                second.release_locks()

    # 4. Doble arranque: el segundo HostController sobre la misma misión falla
    # cerrado por el lock global y no escribe nada.
    def test_double_start_fails_closed(self):
        root = self._root()
        mission = root / 'mission'
        first = HostController(mission)
        first.register_mandate('host-fixture', LIMITS)
        events_after_first = (mission / 'events.jsonl').read_bytes()
        with self.assertRaises(ControllerAlive):
            HostController(mission)
        self.assertEqual((mission / 'events.jsonl').read_bytes(), events_after_first)
        first.release_locks()
        second = HostController(mission)
        self.assertEqual(self._events(mission).count(('CONTROLLER_STARTED', None)), 2)
        second.release_locks()

    # 5. Excepción del turn_launcher: UNIT_RETAINED con causa, candidato
    # conservado, presupuesto conservado y la unidad no se reconsume.
    def test_launcher_exception_retains_with_cause(self):
        root = self._root()
        mission, controller, plans = self._setup(root, ('x',))

        def launch(unit):
            result_path = Path(unit['result_ref'])
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_bytes(plans['x']['result'])  # candidato producido antes del fallo
            raise RuntimeError('boom de turno')

        outcome = controller.run_next(launch)
        self.assertEqual(outcome['unit_id'], 'x')
        self.assertEqual(outcome['outcome'], 'UNIT_RETAINED')
        self.assertIn('boom de turno', outcome['cause'])
        queue = self._queue(mission)
        self.assertEqual(queue['x']['state'], 'RETAINED')
        self.assertIn('boom de turno', queue['x']['retained_cause'])
        self.assertEqual((root / 'artifacts' / 'x' / 'result.json').read_bytes(), plans['x']['result'])
        self.assertIsNone(self._store_tree(mission, 'x'))
        self.assertEqual(controller.budget.usage(), {'attempts': 1, 'cost': 0, 'seconds': 0})
        self.assertEqual(self._events(mission).count(('UNIT_RETAINED', 'x')), 1)
        self.assertEqual(controller.run_all(lambda unit: {'unit_id': unit['unit_id']}),
                         {'done': [], 'retained': []})
        controller.release_locks()

    # 6. cancel() con unidad en vuelo: RETAINED con causa, presupuesto
    # conservado, locks liberados y el estado sigue recuperable.
    def test_cancel_retains_in_flight_unit(self):
        root = self._root()
        mission, controller, plans = self._setup(root, ('c1', 'c2'))
        calls = []
        launch = self._launcher(root, plans, calls)
        with self.assertRaises(Crash):
            controller.run_next(launch, inject=_crash_at('turn_started'))
        self.assertEqual(self._queue(mission)['c1']['state'], 'IN_FLIGHT')
        self.assertEqual(controller.cancel(), {'retained': ['c1']})
        queue = self._queue(mission)
        self.assertEqual(queue['c1']['state'], 'RETAINED')
        self.assertIn('cancel', queue['c1']['retained_cause'])
        self.assertEqual(queue['c2']['state'], 'PENDING')
        self.assertEqual(controller.budget.usage(), {'attempts': 1, 'cost': 0, 'seconds': 0})
        # Locks liberados: un controlador nuevo arranca y continúa desde el estado.
        successor = HostController(mission)
        self.assertEqual(successor.reconcile_on_start(), {'reconciled': []})
        self.assertEqual(successor.run_all(launch), {'done': ['c2'], 'retained': []})
        self.assertEqual(calls, ['c2'])
        self.assertEqual(successor.cancel(), {'retained': []})
        with self.assertRaises(HostError):
            successor.run_next(launch)
        successor.release_locks()

    # 7. Rechazo cerrado: enqueue malformado o duplicado y operaciones sin
    # mandato no escriben nada (cola y diario intactos byte a byte).
    def test_enqueue_rejects_malformed_and_duplicates_without_writes(self):
        root = self._root()
        mission = root / 'mission'
        controller = HostController(mission)
        entry, _ = self._unit(root, 'u1')
        with self.assertRaises(HostError):
            controller.enqueue(entry)
        self.assertFalse((mission / 'queue.json').exists())
        controller.register_mandate('host-fixture', LIMITS)
        self.assertEqual(controller.enqueue(entry), {'unit_id': 'u1', 'state': 'PENDING'})
        queue_bytes = (mission / 'queue.json').read_bytes()
        events_bytes = (mission / 'events.jsonl').read_bytes()
        candidates = [
            dict(entry),  # duplicado
            {key: value for key, value in entry.items() if key != 'result_sha256'},  # incompleto
            dict(entry, unit_id='../escape'),
            dict(entry, task_sha256='no-hash'),
            dict(entry, extra=1),
            dict(entry, cost=True),
            'no-es-objeto',
        ]
        for candidate in candidates:
            with self.subTest(candidate=repr(candidate)[:48]), self.assertRaises(ValueError):
                controller.enqueue(candidate)
        self.assertEqual((mission / 'queue.json').read_bytes(), queue_bytes)
        self.assertEqual((mission / 'events.jsonl').read_bytes(), events_bytes)
        self.assertEqual(len(controller.units()), 1)
        controller.release_locks()



    # 8. Launcher que materializa recibos durante el turno: update_unit_refs
    def test_launcher_materializes_refs_during_turn(self):
        root = self._root()
        mission = root / 'mission'
        hc = HostController(mission)
        hc.register_mandate('host-fixture', LIMITS)
        task_path = root / 'task-late.json'
        result_path = root / 'result-late.json'

        def launcher(unit):
            task_path.write_text(json.dumps({'version': 1, 'unit': unit['unit_id']}))
            result_path.write_text(json.dumps({'version': 1, 'status': 'done'}))
            hc.update_unit_refs(unit['unit_id'], str(task_path), str(result_path))
            return {'artifacts': 'written'}

        hc.enqueue({'unit_id': 'late-1', 'task_ref': 'PENDING', 'result_ref': 'PENDING',
                    'task_sha256': '0' * 64, 'result_sha256': '0' * 64})
        outcome = hc.run_next(launcher)
        self.assertEqual(outcome['outcome'], 'UNIT_DONE')
        self.assertTrue(task_path.exists() and result_path.exists())
        self.assertEqual(self._queue(mission)['late-1']['state'], 'DONE')


if __name__ == '__main__':
    unittest.main()
