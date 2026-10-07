"""Pruebas del ejecutor de workflow U1 (planes gate/join/fase, journal encadenado,
reanudación por replay y retenciones). Todo el trabajo ocurre en /tmp; los gates
son comandos triviales reales invocados por argv, sin shell."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from workflow import WorkflowError, read_journal, run_plan, verify

# shutil.which('python3') y no sys.executable: en este host sys.executable es
# el AppImage de ZCode, que arranca una GUI (convención de test_metrics.py).
PYTHON = shutil.which('python3')

SCRIPT = REPO_ROOT / 'scripts' / 'workflow.py'


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _content_sha256(envelope):
    content = {key: envelope[key] for key in ('version', 'seq', 'event_id', 'kind',
                                              'payload', 'prev_sha256')}
    return hashlib.sha256(_canonical(content)).hexdigest()


class WorkflowExecutorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'

    def write_plan(self, steps, *, filename='plan.json', **extra):
        plan = {'schema_version': 1, 'name': 'prueba', 'workspace': str(self.workspace)}
        plan.update(extra)
        plan['steps'] = steps
        path = self.tmp / filename
        path.write_bytes(_canonical(plan) + b'\n')
        return path

    def gate(self, step_id, command, action='abort', rounds=1):
        return {'id': step_id, 'type': 'gate', 'command': command,
                'on_fail': {'action': action, 'rounds': rounds}}

    def kinds(self, run_dir):
        return [envelope['kind'] for envelope in read_journal(run_dir)]

    def cli(self, *args):
        return subprocess.run([PYTHON, '-B', str(SCRIPT), *args],
                              cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    # -- plan inválido: rechazado sin journal

    def test_plan_invalido_rechazado_sin_journal(self):
        cases = [
            {'schema_version': 2, 'name': 'x', 'workspace': str(self.workspace), 'steps': []},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace)},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace), 'steps': [],
             'ajena': 1},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace), 'steps': {}},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.tmp / 'no-existe'),
             'steps': [self.gate('g1', ['true'])]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [self.gate('tiene espacios', ['true'])]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [self.gate('g1', ['true']), self.gate('g1', ['true'])]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'despliegue', 'command': ['true']}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': 'true',
                        'on_fail': {'action': 'abort'}}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': [],
                        'on_fail': {'action': 'abort'}}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'reiniciar'}}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'retry'}}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'retry', 'rounds': 1}},
                       {'id': 'j1', 'type': 'join'}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'abort', 'rounds': 1}, 'depends': ['g2']},
                       {'id': 'g2', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'abort', 'rounds': 1}}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'g1', 'type': 'gate', 'command': ['true'],
                        'on_fail': {'action': 'abort'}, 'depends': ['inexistente']}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'f1', 'type': 'fase'}]},
            {'schema_version': 1, 'name': 'x', 'workspace': str(self.workspace),
             'steps': [{'id': 'a1', 'type': 'ask', 'prompt': 'p', 'prompt_file': 'f'}]},
        ]
        for index, value in enumerate(cases):
            with self.subTest(case=index):
                path = self.tmp / ('invalido-%d.json' % index)
                path.write_bytes(_canonical(value) + b'\n')
                with self.assertRaises(WorkflowError):
                    run_plan(path)
                self.assertFalse(self.run_root.exists())
        proc = self.cli('run', str(path))
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith('workflow: '))
        self.assertFalse(self.run_root.exists())

    # -- verify sobre cadena íntegra

    def test_verify_ok_sobre_cadena_integra(self):
        plan_path = self.write_plan([self.gate('g1', ['true']),
                                     self.gate('g2', ['echo', 'hola'])])
        raw = plan_path.read_bytes()
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'COMPLETED')
        run_dir = Path(outcome['run_dir'])
        payloads = read_journal(run_dir)
        self.assertEqual(payloads[0]['kind'], 'PLAN_LOADED')
        loaded = payloads[0]['payload']
        self.assertEqual(loaded['plan_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(loaded['run_id'], 'r-' + hashlib.sha256(raw).hexdigest()[:24])
        self.assertEqual(loaded['steps'], 2)
        self.assertEqual((run_dir / 'plan.snapshot.json').read_bytes(), raw)
        info = verify(run_dir)
        self.assertEqual(info['events'], len(payloads))
        self.assertEqual(info['head_sha256'], payloads[-1]['content_sha256'])
        proc = self.cli('verify', str(run_dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['result'], 'VERIFIED')
        self.assertEqual(oct(self.run_root.stat().st_mode & 0o777), '0o700')

    # -- verify ante alterado, truncado y prolongado

    def test_verify_falla_ante_alterado_truncado_y_prolongado(self):
        plan_path = self.write_plan([self.gate('g1', ['true'])])
        outcome = run_plan(plan_path)
        run_dir = Path(outcome['run_dir'])
        journal = run_dir / 'journal.jsonl'
        original = journal.read_bytes()
        lines = original.splitlines(keepends=True)

        envelope = json.loads(lines[1])
        envelope['payload']['attempt'] = 99
        journal.write_bytes(b''.join([lines[0], _canonical(envelope) + b'\n']))
        with self.assertRaisesRegex(WorkflowError, 'registro alterado'):
            verify(run_dir)
        proc = self.cli('verify', str(run_dir))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith('workflow: '))

        journal.write_bytes(b''.join(lines[:-1]))
        with self.assertRaisesRegex(WorkflowError, 'Digest global no coincide'):
            verify(run_dir)

        last = json.loads(lines[-1])
        forged = {'version': 1, 'seq': len(lines), 'event_id': 'e-forged',
                  'kind': 'RUN_COMPLETED', 'payload': {}, 'prev_sha256': last['content_sha256']}
        forged['content_sha256'] = _content_sha256(forged)
        journal.write_bytes(original + _canonical(forged) + b'\n')
        with self.assertRaisesRegex(WorkflowError, 'Digest global no coincide'):
            verify(run_dir)

    # -- reanudación por replay: solo se salta STEP_COMPLETED verificado

    def test_replay_salta_solo_step_completed(self):
        flag = self.tmp / 'bandera'
        plan_path = self.write_plan([self.gate('s1', ['true']),
                                     self.gate('s2', ['test', '-f', str(flag)])])
        first = run_plan(plan_path)
        self.assertEqual(first['result'], 'RETAINED')
        self.assertEqual(first['cause'], 'gate-abort:s2')
        self.assertNotIn('RUN_COMPLETED', self.kinds(first['run_dir']))

        flag.write_text('x')
        second = run_plan(plan_path)
        self.assertEqual(second['result'], 'COMPLETED')
        payloads = read_journal(second['run_dir'])
        started_s1 = [e for e in payloads if e['kind'] == 'STEP_STARTED'
                      and e['payload']['step_id'] == 's1']
        self.assertEqual(len(started_s1), 1, 's1 verificado no debe re-ejecutarse')
        completed_s1 = [e for e in payloads if e['kind'] == 'STEP_COMPLETED'
                        and e['payload']['step_id'] == 's1']
        self.assertEqual(len(completed_s1), 1)
        attempts_s2 = [e['payload']['attempt'] for e in payloads
                       if e['kind'] == 'STEP_STARTED' and e['payload']['step_id'] == 's2']
        self.assertEqual(attempts_s2, [1, 2], 's2 sin STEP_COMPLETED se re-ejecuta')
        self.assertIn('RUN_RETAINED', [e['kind'] for e in payloads])
        self.assertEqual(payloads[-1]['kind'], 'RUN_COMPLETED')
        self.assertEqual(verify(second['run_dir'])['events'], len(payloads))

    # -- gate FAIL con retry: GATE_REJECTED x N + ROUND_CAP_REACHED + RUN_RETAINED

    def test_gate_fail_con_rounds_agota_y_retina(self):
        plan_path = self.write_plan([self.gate('g1', ['false'], action='retry', rounds=3)])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'gate-rounds-exhausted:g1')
        self.assertTrue(outcome['journaled'])
        payloads = read_journal(outcome['run_dir'])
        kinds = [e['kind'] for e in payloads]
        self.assertEqual(kinds.count('GATE_REJECTED'), 3)
        self.assertEqual(kinds.count('STEP_STARTED'), 3)
        self.assertEqual([e['payload']['attempt'] for e in payloads
                          if e['kind'] == 'STEP_STARTED'], [1, 2, 3])
        self.assertEqual(kinds.count('ROUND_CAP_REACHED'), 1)
        self.assertEqual(kinds.count('RUN_RETAINED'), 1)
        self.assertNotIn('STEP_COMPLETED', kinds)
        rejected = [e['payload'] for e in payloads if e['kind'] == 'GATE_REJECTED']
        for payload in rejected:
            self.assertEqual(payload['exit_code'], 1)
            observation = Path(outcome['run_dir']) / payload['observation']
            self.assertTrue(observation.is_file())
            digest = hashlib.sha256(observation.read_bytes()).hexdigest()
            self.assertEqual(digest, payload['output_sha256'])

        cli_plan = self.write_plan([self.gate('g1', ['false'], action='retry', rounds=2)],
                                   filename='cli-rounds.json')
        proc = self.cli('run', str(cli_plan))
        self.assertEqual(proc.returncode, 1)
        emitted = json.loads(proc.stderr)
        self.assertEqual(emitted['result'], 'RETAINED')
        self.assertEqual(emitted['cause'], 'gate-rounds-exhausted:g1')

    # -- comando inexistente y exit >= 2: IMPOSSIBLE -> RETAINED

    def test_gate_imposible_comando_inexistente_y_exit_2(self):
        plan_path = self.write_plan([self.gate('g1', ['comando-inexistente-xyz'])])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'gate-impossible:g1:spawn')
        kinds = self.kinds(outcome['run_dir'])
        self.assertNotIn('GATE_REJECTED', kinds)
        self.assertNotIn('STEP_COMPLETED', kinds)

        plan_path = self.write_plan(
            [self.gate('g1', [PYTHON, '-B', '-c', 'import sys; sys.exit(2)'])],
            filename='exit2.json')
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'gate-impossible:g1:exit=2')
        kinds = self.kinds(outcome['run_dir'])
        self.assertNotIn('GATE_REJECTED', kinds)
        self.assertNotIn('STEP_COMPLETED', kinds)

    # -- join con dep fallido -> RETAINED

    def test_join_con_dep_fallido_retina(self):
        plan_path = self.write_plan([self.gate('d1', ['false'], action='continue'),
                                     {'id': 'j1', 'type': 'join', 'depends': ['d1']}])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'join-dep-not-completed:j1:d1')
        payloads = read_journal(outcome['run_dir'])
        kinds = [e['kind'] for e in payloads]
        self.assertEqual(kinds.count('GATE_REJECTED'), 1)
        failed = [e['payload'] for e in payloads if e['kind'] == 'STEP_FAILED']
        self.assertEqual([payload['action'] for payload in failed], ['continue'])
        self.assertNotIn('STEP_COMPLETED', kinds)
        self.assertNotIn('RUN_COMPLETED', kinds)

    # -- join exitoso: resultado con digest de cada dep

    def test_join_exitoso_registra_digests_de_deps(self):
        plan_path = self.write_plan([self.gate('a', ['true']), self.gate('b', ['true']),
                                     {'id': 'j', 'type': 'join', 'depends': ['a', 'b']}])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'COMPLETED')
        payloads = read_journal(outcome['run_dir'])
        digests = {e['payload']['step_id']: e['payload']['output_sha256']
                   for e in payloads if e['kind'] == 'STEP_COMPLETED'}
        join = [e['payload'] for e in payloads
                if e['kind'] == 'STEP_COMPLETED' and e['payload']['step_id'] == 'j'][0]
        self.assertEqual(join['deps'],
                         {'a': digests['a'], 'b': digests['b']})
        observations = sorted(entry.name for entry in
                              (Path(outcome['run_dir']) / 'observations').iterdir())
        self.assertEqual(observations,
                         ['01-a-gate.json', '02-b-gate.json', '03-j-join.json'])
        join_observation = json.loads((Path(outcome['run_dir']) / 'observations' /
                                       '03-j-join.json').read_bytes())
        self.assertEqual(join_observation['deps'], join['deps'])
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    # -- tope del almacén (inyectable) -> RETAINED sin truncar

    def test_tope_de_almacen_retina_con_cap_inyectable(self):
        plan_path = self.write_plan([self.gate('g1', ['false'], action='retry', rounds=200)])
        outcome = run_plan(plan_path, journal_limit=6000)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'journal-store-limit')
        self.assertTrue(outcome['journaled'])
        journal = Path(outcome['run_dir']) / 'journal.jsonl'
        raw = journal.read_bytes()
        self.assertLessEqual(len(raw), 6000)
        payloads = read_journal(outcome['run_dir'])
        kinds = [e['kind'] for e in payloads]
        rejections = kinds.count('GATE_REJECTED')
        self.assertGreaterEqual(rejections, 1)
        self.assertLess(rejections, 200)
        self.assertEqual(kinds[-1], 'RUN_RETAINED')
        self.assertEqual(payloads[-1]['payload']['cause'], 'journal-store-limit')
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    # -- registro mayor que 4096 B -> RETAINED sin truncar

    def test_registro_mayor_que_4096_retina(self):
        deps = ['g%02d' % index for index in range(60)]
        steps = [self.gate(dep, ['true']) for dep in deps]
        steps.append({'id': 'j', 'type': 'join', 'depends': deps})
        plan_path = self.write_plan(steps)
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'journal-record-limit:j')
        payloads = read_journal(outcome['run_dir'])
        kinds = [e['kind'] for e in payloads]
        self.assertEqual(kinds[-1], 'RUN_RETAINED')
        completed = [e['payload']['step_id'] for e in payloads
                     if e['kind'] == 'STEP_COMPLETED']
        self.assertNotIn('j', completed)
        for line in (Path(outcome['run_dir']) / 'journal.jsonl').read_bytes().splitlines():
            self.assertLessEqual(len(line), 4096)
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    # -- plan gate-only por CLI: RUN_COMPLETED, exit 0

    def test_plan_gate_only_por_cli_run_completed(self):
        plan_path = self.write_plan([self.gate('g1', ['true'])])
        proc = self.cli('run', str(plan_path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        emitted = json.loads(proc.stdout)
        self.assertEqual(emitted['result'], 'COMPLETED')
        payloads = read_journal(emitted['run_dir'])
        self.assertEqual(payloads[-1]['kind'], 'RUN_COMPLETED')
        self.assertEqual([e['kind'] for e in payloads],
                         ['PLAN_LOADED', 'STEP_STARTED', 'STEP_COMPLETED', 'RUN_COMPLETED'])
        proc = self.cli('verify', emitted['run_dir'])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- plan con ask sin cliente: ABSTAINED, exit 1, sin run dir

    def test_plan_con_ask_sin_cliente_abstiene(self):
        plan_path = self.write_plan([self.gate('g1', ['true']),
                                     {'id': 'a1', 'type': 'ask', 'prompt': 'resume'}])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'ABSTAINED')
        self.assertIn('ask', outcome['reason'])
        self.assertFalse(self.run_root.exists())

        # U3: prompt_file se resuelve al cargar el plan (fail-closed antes
        # de run dir), así que el fichero debe existir para llegar a la
        # abstención por falta de cliente.
        (self.tmp / 'prompt.txt').write_text('resume el informe', encoding='utf-8')
        plan_path = self.write_plan([{'id': 'a1', 'type': 'ask', 'prompt_file': 'prompt.txt'}],
                                    filename='ask-file.json')
        proc = self.cli('run', str(plan_path))
        self.assertEqual(proc.returncode, 1)
        emitted = json.loads(proc.stderr)
        self.assertEqual(emitted['result'], 'ABSTAINED')
        self.assertIn('ask', emitted['reason'])
        self.assertEqual(proc.stdout, '')
        self.assertFalse(self.run_root.exists())

        # prompt_file ausente: error de plan antes de run dir (U3).
        plan_path = self.write_plan([{'id': 'a1', 'type': 'ask', 'prompt_file': 'ausente.txt'}],
                                    filename='ask-ausente.json')
        with self.assertRaises(WorkflowError):
            run_plan(plan_path)
        self.assertFalse(self.run_root.exists())

        plan_path = self.write_plan([{'id': 'a1', 'type': 'ask'}],
                                    filename='ask-invalido.json')
        with self.assertRaises(WorkflowError):
            run_plan(plan_path)
        self.assertFalse(self.run_root.exists())

    # -- fase: cuenta GATE_REJECTED desde su inicio; excedido -> RETAINED

    def test_fase_cuenta_rechazos_y_retina_al_exceder(self):
        plan_path = self.write_plan([{'id': 'f1', 'type': 'fase', 'name': 'core',
                                      'max_rounds': 1},
                                     self.gate('g1', ['false'], action='continue'),
                                     self.gate('g2', ['false'], action='continue')])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'fase-rounds-exceeded:core')
        kinds = self.kinds(outcome['run_dir'])
        self.assertEqual(kinds.count('PHASE_STARTED'), 1)
        self.assertEqual(kinds.count('GATE_REJECTED'), 2)
        self.assertNotIn('ROUND_CAP_REACHED', kinds)
        self.assertNotIn('RUN_COMPLETED', kinds)

        plan_path = self.write_plan([{'id': 'f1', 'type': 'fase', 'name': 'core'},
                                     self.gate('g1', ['true'])],
                                    filename='fase-ok.json')
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'COMPLETED')
        self.assertIn('PHASE_STARTED', self.kinds(outcome['run_dir']))

    # -- reanudación sobre journal alterado: falla cerrada sin escribir

    def test_reanudacion_sobre_journal_alterado_falla_cerrado(self):
        plan_path = self.write_plan([self.gate('g1', ['true'])])
        outcome = run_plan(plan_path)
        self.assertEqual(outcome['result'], 'COMPLETED')
        journal = Path(outcome['run_dir']) / 'journal.jsonl'
        lines = journal.read_bytes().splitlines(keepends=True)
        envelope = json.loads(lines[1])
        envelope['payload']['step_type'] = 'join'
        lines[1] = _canonical(envelope) + b'\n'
        altered = b''.join(lines)
        journal.write_bytes(altered)
        with self.assertRaisesRegex(WorkflowError, 'registro alterado'):
            run_plan(plan_path)
        self.assertEqual(journal.read_bytes(), altered)


if __name__ == '__main__':
    unittest.main()
