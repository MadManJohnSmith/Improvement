"""Memoria incremental entre campañas (U7): dónde mide, dónde invalida y dónde
no decide. Todo el trabajo ocurre en /tmp; el producto es un repo git real y
sintético, y los gates son comandos triviales invocados por argv, sin shell."""
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

import workflow
import workflow_evidence
from workflow import WorkflowError, read_journal, run_plan, verify

sys.path.insert(0, str(REPO_ROOT / 'tests'))

from test_workflow_ask import FakeAskClient, _write_result  # noqa: E402

# shutil.which y no sys.executable: sys.executable puede ser el AppImage de ZCode.
PYTHON = shutil.which('python3')
FAKE_PRESET = 'cordis'


def _git(product, *args):
    subprocess.run(['git', '-C', str(product), *args], check=True,
                   capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME='prueba',
                            GIT_AUTHOR_EMAIL='p@e', GIT_COMMITTER_NAME='prueba',
                            GIT_COMMITTER_EMAIL='p@e'))


class MemoryProduct:
    """Fixture: repo git con un fichero base y un workspace que lo declara."""

    def __init__(self, root):
        self.root = Path(root)
        self.product = self.root / 'producto'
        self.workspace = self.root / 'workspace'
        self.product.mkdir(parents=True)
        self.workspace.mkdir(parents=True)
        (self.product / 'base.txt').write_text('uno\n', encoding='utf-8')
        (self.workspace / 'project.json').write_text(
            json.dumps({'schema': 1, 'name': 'demo',
                        'project': str(self.product)}, ensure_ascii=False),
            encoding='utf-8')

    def init_git(self):
        subprocess.run(['git', 'init', '-q', str(self.product)], check=True)
        _git(self.product, 'add', '-A')
        _git(self.product, 'commit', '-qm', 'base')

    def commit(self, message):
        _git(self.product, 'add', '-A')
        _git(self.product, 'commit', '-qm', message)

    def edit(self, name, text):
        (self.product / name).write_text(text, encoding='utf-8')


class WorkflowMemoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.product = MemoryProduct(self.tmp / 'producto-fixture')
        self.product.init_git()
        self.run_root = self.tmp / 'runs'

    # -- helpers

    def plan_path(self, steps, *, memory=True, name='campana-memoria'):
        plan = {'schema_version': 1, 'name': name,
                'workspace': str(self.product.workspace),
                'run_root': str(self.run_root), 'steps': steps,
                # Los planes con ask pasan el preflight de preset verificado;
                # sin declararlo se abstendrían antes de tocar disco.
                'preset': FAKE_PRESET}
        if memory:
            plan['memory'] = True
        path = self.tmp / (name + '.json')
        path.write_bytes(json.dumps(plan, sort_keys=True,
                                    separators=(',', ':')).encode() + b'\n')
        return path

    def passing_gate(self, step_id):
        return {'id': step_id, 'type': 'gate',
                'command': [PYTHON, '-c', 'import sys; sys.exit(0)'],
                'on_fail': {'action': 'abort', 'rounds': 1}}

    def failing_gate(self, step_id):
        return {'id': step_id, 'type': 'gate',
                'command': [PYTHON, '-c', 'import sys; sys.exit(1)'],
                'on_fail': {'action': 'abort', 'rounds': 1}}

    def memory_record(self, run_dir):
        records = [item for item in read_journal(run_dir)
                   if item['kind'] == 'MEMORY_RECONCILED']
        self.assertTrue(records, 'sin MEMORY_RECONCILED en el journal')
        # registers[0] describe el arranque de la campaña; el último es el que
        # corresponde a la reanudación cuando reejecutamos el mismo plan.
        return records[-1]['payload']

    # -- la memoria nunca decide: ni salta pasos ni veredictos

    def test_memoria_no_salta_pasos_ni_veredictos(self):
        """Con memoria publicada y todo igual, el gate se vuelve a ejecutar."""
        first = run_plan(self.plan_path([self.passing_gate('g1')]),
                         run_root=self.run_root)
        self.assertEqual(first['result'], 'COMPLETED')
        self.assertTrue((self.run_root / 'g1').exists()
                        if False else (self.run_root / 'memory.json').is_file(),
                        'la campaña completada debe publicar memoria')

        ran = self.tmp / 'ran.txt'
        gate = {'id': 'g1', 'type': 'gate',
                'command': [PYTHON, '-c',
                            'import pathlib; p=pathlib.Path(%r);'
                            'p.write_text("1") if not p.exists() else None' % str(ran)],
                'on_fail': {'action': 'abort', 'rounds': 1}}
        second = run_plan(self.plan_path([gate]), run_root=self.run_root)
        self.assertEqual(second['result'], 'COMPLETED')
        self.assertTrue(ran.is_file(),
                        'la memoria no puede sustituir la ejecución del gate')

    def test_memoria_no_publica_en_run_retenido(self):
        gate = {'id': 'g1', 'type': 'gate',
                'command': [PYTHON, '-c', 'import sys; sys.exit(1)'],
                'on_fail': {'action': 'abort', 'rounds': 1}}
        outcome = run_plan(self.plan_path([gate]), run_root=self.run_root)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertFalse((self.run_root / 'memory.json').is_file(),
                         'un run RETAINED no deja memoria reutilizable')
        self.assertEqual([item['kind'] for item in read_journal(outcome['run_dir'])][-1],
                         'RUN_RETAINED')

    def test_memoria_no_cosecha_veredictos(self):
        """La memoria no contiene ningún veredicto: un run que publique un
        veredicto en evidence/ no deja ese veredicto en la memoria."""
        evidence = self.product.workspace / 'evidence'
        evidence.mkdir(parents=True)
        (evidence / 'veredicto.json').write_text(
            json.dumps({'verdict': 'PASS', 'records': 3}), encoding='utf-8')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED')
        memory = (self.run_root / 'memory.json').read_text(encoding='utf-8')
        self.assertNotIn('verdict', memory)
        self.assertNotIn('PASS', memory)
        # evidence/ no es parte del producto: el inventario ignora su contenido
        self.assertNotIn('evidence', memory)

    # -- invalidación fail-closed

    def test_invalidacion_por_cambio_de_fichero(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        self.product.edit('base.txt', 'uno modificado\n')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['hits'], 0)
        self.assertEqual(record['invalidated'], 0)
        self.assertEqual(record['misses'], 1)

    def test_invalidacion_por_cambio_de_base(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        self.product.edit('base.txt', 'dos\n')
        self.product.commit('segundo')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['hits'], 0)
        self.assertEqual(record['invalidated'], 1,
                         'el contexto distinto invalida todo el grupo anterior')

    def test_invalidacion_por_borrado(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        (self.product.product / 'base.txt').unlink()
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['invalidated'], 1)
        self.assertEqual(record['hits'], 0)

    def test_invalidacion_por_rename(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        (self.product.product / 'base.txt').rename(self.product.product / 'nuevo.txt')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        # El contenido es el mismo, pero la evidencia está ligada a ruta +
        # digest: un nombre nuevo es un fichero que nadie verificó, así que no
        # hay hit posible. Es el comportamiento conservador correcto.
        self.assertEqual(record['hits'], 0,
                         'una ruta nueva no es una ruta verificada')
        self.assertEqual(record['misses'], 1,
                         'el nombre nuevo entra como fallo')
        self.assertEqual(record['invalidated'], 1,
                         'el nombre antiguo desaparece del inventario')

    def test_invalidacion_por_config(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        (self.product.workspace / 'base.json').write_text(
            json.dumps({'base': '4242424242424242424242424242424242424242'}),
            encoding='utf-8')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['hits'], 0)
        self.assertEqual(record['invalidated'], 1,
                         'la configuración vinculada forma parte del contexto')

    def test_invalidacion_por_exclusion(self):
        """Un fichero bajo un directorio de estado generado sale del contexto:
        añadirlo no crea misses, y la campaña sigue midiendo el producto."""
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        state = self.product.workspace / 'evidence' / 'campana'
        state.mkdir(parents=True)
        (state / 'veredicto.json').write_text('{"verdict": "PASS"}',
                                              encoding='utf-8')
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['hits'], 1,
                         'evidence/ es estado generado y no entra en el inventario')
        self.assertEqual(record['misses'], 0)
        self.assertEqual(record['invalidated'], 0)

    def test_symlink_inventariado_invalida_todo(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        link = self.product.product / 'enlace'
        link.symlink_to('/etc/passwd')
        with self.assertRaises(workflow_evidence.EvidenceError) as caught:
            workflow_evidence.snapshot(self.product.workspace)
        self.assertIn('symlink', str(caught.exception))

    def test_evidencia_maliciosa_memoria_ilegible(self):
        """Una memoria con entradas inválidas se descarta entera, no a medias."""
        target = self.run_root / 'memory.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            'kind': 'workflow-memory', 'version': 1,
            'workspace': '/nonexistente', 'product': '/nonexistente',
            'base': 'a' * 40, 'config': 'b' * 64,
            'files': {'../../etc/passwd': 'zzz'},
            'sizes': {'../../etc/passwd': 12},
        }, sort_keys=True), encoding='utf-8')
        hint = workflow_evidence.reconcile_hint(self.product.workspace, target)
        # La memoria válida no existe: campaña sin memoria, no memoria deforme.
        self.assertEqual(hint['hits'], 0)
        self.assertLessEqual(hint['misses'], 1)

    def test_memoria_solo_escribe_en_run_root_fuera_del_workspace(self):
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        for candidate in (self.product.workspace / 'memory.json',
                          self.product.product / 'memory.json'):
            self.assertFalse(candidate.exists(),
                             'la memoria jamás se escribe dentro del workspace '
                             'ni del producto: ' + str(candidate))

    # -- dos corridas: idempotencia y diferenciación

    def test_dos_corridas_mismo_plan_reaundan_mismo_run_dir(self):
        plan = self.plan_path([self.passing_gate('g1')])
        first = run_plan(plan, run_root=self.run_root)
        first_kinds = [item['kind'] for item in read_journal(first['run_dir'])]
        second = run_plan(plan, run_root=self.run_root)
        self.assertEqual(Path(first['run_dir']), Path(second['run_dir']),
                         'el mismo plan reanuda el mismo run dir')
        kinds = [item['kind'] for item in read_journal(second['run_dir'])]
        # Idempotencia real: la reanudación solo añade su medida de memoria
        # y su cierre. Ningún paso se repite.
        self.assertEqual(kinds[:len(first_kinds)], first_kinds)
        self.assertEqual(kinds[len(first_kinds):], ['MEMORY_RECONCILED', 'RUN_COMPLETED'])
        self.assertEqual(len([k for k in kinds if k == 'STEP_STARTED']), 1,
                         'ningún paso se vuelve a ejecutar en la reanudación')

    def test_dos_corridas_distinto_plan_no_reutiliza_run(self):
        first = run_plan(self.plan_path([self.passing_gate('g1'), self.passing_gate('g2')],
                                        name='campana-a'),
                         run_root=self.run_root)
        second = run_plan(self.plan_path([self.passing_gate('g1')],
                                         name='campana-b'),
                          run_root=self.run_root)
        self.assertNotEqual(Path(first['run_dir']), Path(second['run_dir']),
                            'planes distintos son corridas distintas')
        record = self.memory_record(second['run_dir'])
        self.assertEqual(record['hits'], 1,
                         'el run nuevo comparte pistas del mismo workspace')
        self.assertEqual(record['misses'], 0)

    # -- mide hits, misses y costes sin inventar tokens

    def test_mide_hits_misses_y_bytes_reales(self):
        run_plan(self.plan_path([self.passing_gate('g1')]), run_root=self.run_root)
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        record = self.memory_record(outcome['run_dir'])
        self.assertEqual(record['hits'], 1)
        self.assertEqual(record['misses'], 0)
        self.assertEqual(record['invalidated'], 0)
        self.assertEqual(record['bytes_saved'],
                         len('uno\n'), 'bytes son el tamaño real del fichero')
        self.assertIsNone(record['tokens_saved'],
                          'el Host no cuenta tokens: nunca se inventa la cifra')

    # -- el ejecutor sigue siendo verificable

    def test_verify_con_memoria_publicada(self):
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        info = verify(outcome['run_dir'])
        self.assertEqual(info['events'], 5, info)
        self.assertEqual([item['kind'] for item in read_journal(outcome['run_dir'])][-1],
                         'RUN_COMPLETED')

    def test_journal_alterado_con_memoria_sigue_fallando_cerrado(self):
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        journal = Path(outcome['run_dir']) / 'journal.jsonl'
        lines = journal.read_bytes().split(b'\n')
        # La segunda línea es MEMORY_RECONCILED. Cambiar un byte sin
        # recalcular el hash rompe la cadena, y verify debe detectarlo.
        self.assertIn(b'"hits":0', lines[1])
        lines[1] = lines[1].replace(b'"hits":0', b'"hits":9')
        journal.write_bytes(b'\n'.join(lines))
        with self.assertRaises(WorkflowError):
            verify(outcome['run_dir'])

    def test_plan_rechaza_memory_no_booleano(self):
        plan = {'schema_version': 1, 'name': 'x',
                'workspace': str(self.product.workspace),
                'run_root': str(self.run_root),
                'memory': 'si', 'steps': [self.passing_gate('g1')]}
        path = self.tmp / 'memory-invalida.json'
        path.write_bytes(json.dumps(plan, sort_keys=True,
                                    separators=(',', ':')).encode() + b'\n')
        with self.assertRaises(WorkflowError):
            run_plan(path, run_root=self.run_root)

    def test_memoria_ausente_no_impide_campana(self):
        """Sin memoria previa, la campaña arranca y lo dice con misses=inventario."""
        outcome = run_plan(self.plan_path([self.passing_gate('g1')],
                                         memory=False),
                           run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED')
        self.assertFalse((self.run_root / 'memory.json').is_file(),
                         'un plan sin memory no publica nada')
        self.assertNotIn('MEMORY_RECONCILED',
                         [item['kind'] for item in read_journal(outcome['run_dir'])])

    # -- FAIL -> repair, probado end-to-end con cliente DSH falso

    def test_fail_to_repair_ciclo_completo(self):
        """FAIL real del gate -> despacho de reparación -> PASS final.

        El gate público lee el veredicto real que el reparador dejó en
        evidence/; mientras sea FAIL sale 1, y al reescribirse sale 0.
        """
        verify_gate = self.tmp / 'verify_gate.py'
        verify_gate.write_text(
            'import json, pathlib, sys\n'
            'data = json.loads(pathlib.Path("evidence/campana/veredicto.json").read_text())\n'
            'sys.exit(0 if data["verdict"] == "PASS" else 1)\n', encoding='utf-8')
        prompt = self.tmp / 'prompt.md'
        prompt.write_text('# reparar el candidato\n', encoding='utf-8')
        evidence = self.product.workspace / 'evidence' / 'campana'
        evidence.mkdir(parents=True)
        (evidence / 'veredicto.json').write_text(
            json.dumps({'verdict': 'FAIL', 'records': 3}), encoding='utf-8')
        (evidence / 'reparar.json').write_text(
            json.dumps({'repaired': False}), encoding='utf-8')

        def reparar(workspace):
            _write_result(workspace, 'campana/reparar.json',
                          {'repaired': True,
                           'items': [{'finding_id': 'F1', 'status': 'RESOLVED'}]})
            (Path(workspace) / 'evidence' / 'campana' / 'veredicto.json').write_text(
                json.dumps({'verdict': 'PASS', 'records': 2}), encoding='utf-8')

        plan = self.plan_path([
            {'id': 'verificar-pre', 'type': 'gate',
             'command': [PYTHON, str(verify_gate)],
             'on_fail': {'action': 'continue', 'rounds': 1}},
            {'id': 'reparar-1', 'type': 'ask', 'prompt': prompt.read_text(),
             'timeout_s': 30,
             'result_contract': {'path': 'reparar.json', 'evidence_name': 'campana'},
             'if_veredicto': {'from': 'verificar-pre', 'path': 'veredicto.json',
                              'field': 'verdict', 'equals': 'FAIL'}},
            {'id': 'verificar-final', 'type': 'gate',
             'command': [PYTHON, str(verify_gate)],
             'on_fail': {'action': 'abort', 'rounds': 1}},
        ])
        client = FakeAskClient()
        client.complete_after = 1
        client.on_complete = lambda session: reparar(session.workspace)
        outcome = run_plan(plan, ask_client=client, run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED', outcome.get('cause'))
        payloads = [item['kind'] for item in read_journal(outcome['run_dir'])]
        self.assertEqual(payloads[:2], ['PLAN_LOADED', 'MEMORY_RECONCILED'])
        self.assertIn('GATE_REJECTED', payloads,
                      'el gate previo debe haber fallado de verdad')
        self.assertEqual(len([item for item in payloads if item == 'STEP_STARTED']), 3)
        self.assertIn('STEP_COMPLETED', payloads)
        self.assertEqual(payloads[-1], 'RUN_COMPLETED')
        self.assertEqual(len(client.created), 1, 'una única sesión de reparación')
        self.assertEqual(len(client.sent), 1)

    def test_fail_to_repair_resume_entre_campanas(self):
        """La misma campaña reanudada no vuelve a despachar la reparación."""
        verify_gate = self.tmp / 'verify_gate2.py'
        verify_gate.write_text(
            'import json, pathlib, sys\n'
            'data = json.loads(pathlib.Path("evidence/campana/veredicto.json").read_text())\n'
            'sys.exit(0 if data["verdict"] == "PASS" else 1)\n', encoding='utf-8')
        prompt = self.tmp / 'prompt.md'
        prompt.write_text('# reparar el candidato\n', encoding='utf-8')
        evidence = self.product.workspace / 'evidence' / 'campana'
        evidence.mkdir(parents=True)
        (evidence / 'veredicto.json').write_text(
            json.dumps({'verdict': 'FAIL', 'records': 3}), encoding='utf-8')
        (evidence / 'reparar.json').write_text(
            json.dumps({'repaired': False}), encoding='utf-8')

        def reparar(workspace):
            _write_result(workspace, 'campana/reparar.json',
                          {'repaired': True,
                           'items': [{'finding_id': 'F1', 'status': 'RESOLVED'}]})
            (Path(workspace) / 'evidence' / 'campana' / 'veredicto.json').write_text(
                json.dumps({'verdict': 'PASS', 'records': 2}), encoding='utf-8')

        plan = self.plan_path([
            {'id': 'verificar-pre', 'type': 'gate',
             'command': [PYTHON, str(verify_gate)],
             'on_fail': {'action': 'continue', 'rounds': 1}},
            {'id': 'reparar-1', 'type': 'ask', 'prompt': prompt.read_text(),
             'timeout_s': 30,
             'result_contract': {'path': 'reparar.json', 'evidence_name': 'campana'},
             'if_veredicto': {'from': 'verificar-pre', 'path': 'veredicto.json',
                              'field': 'verdict', 'equals': 'FAIL'}},
            {'id': 'verificar-final', 'type': 'gate',
             'command': [PYTHON, str(verify_gate)],
             'on_fail': {'action': 'abort', 'rounds': 1}},
        ])
        client = FakeAskClient()
        client.complete_after = 1
        client.on_complete = lambda session: reparar(session.workspace)
        first = run_plan(plan, ask_client=client, run_root=self.run_root)
        self.assertEqual(first['result'], 'COMPLETED', first.get('cause'))
        self.assertEqual(len(client.created), 1)

        # El veredicto daña el producto entre campañas: la campaña siguiente
        # reanuda el MISMO run dir sin re-despachar la reparación.
        self.product.edit('base.txt', 'uno modificado\n')
        second = run_plan(plan, ask_client=client, run_root=self.run_root)
        self.assertEqual(second['result'], 'COMPLETED', second.get('cause'))
        self.assertEqual(len(client.created), 1,
                         'la reanudación no re-despacha un turno terminado')
        self.assertEqual(len(client.sent), 1)
        kinds = [item['kind'] for item in read_journal(second['run_dir'])]
        self.assertEqual(kinds.count('STEP_STARTED'), 3,
                         'la reanudación no repite ninguna de las tres acciones')
        self.assertEqual(kinds.count('RUN_COMPLETED'), 2,
                         'ambas invocaciones cierran en el mismo journal')

    def test_verify_con_journal_de_memoria(self):
        """MEMORY_RECONCILED viaja en el journal verificado y no rompe verify."""
        outcome = run_plan(self.plan_path([self.passing_gate('g1')]),
                           run_root=self.run_root)
        info = verify(outcome['run_dir'])
        self.assertEqual(info['events'], 5, info)
        self.assertIn('MEMORY_RECONCILED',
                      [item['kind'] for item in read_journal(outcome['run_dir'])])


if __name__ == '__main__':
    unittest.main()
