"""Regresiones del gate de campaña (U6b): PASS con ledger vivo, FAIL cuando el
registro no casa con la candidata vigente, BLOCKED cuando falta una capability o
el plan de capacidades es ilegible, abstención del preflight sin cliente DSH, y
la garantía de que el wrapper nunca escribe el ledger de verificación. Todo el
trabajo ocurre en /tmp."""
import contextlib
import io
import json
import sys
import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import campaign
import stack


HEAD = 'a' * 40
DIFF = 'b' * 64
# Nombre de toolchain que no existe en ninguna máquina: el stack declarado con
# esta capability queda BLOCKED siempre, sin depender de qué tenga el host.
ABSENT = 'herramienta-inexistente-campana'


class CampaignGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'producto'
        self.workspace.mkdir()
        self.state = self.workspace / 'mode-state'
        self.state.mkdir()
        (self.workspace / 'manage.py').write_text('#!/usr/bin/env python3\n')
        (self.workspace / 'requirements.txt').write_text('django\n')
        (self.workspace / 'web').mkdir()
        (self.workspace / 'web' / 'package-lock.json').write_text('{"lockfileVersion": 3}\n')
        self.write_candidate()
        self.write_plan()

    # -- construcción del workspace sintético

    def write_candidate(self, *, head=HEAD, diff=DIFF):
        (self.state / 'work-items.json').write_text(json.dumps({
            'schema_version': 1,
            'candidate': {'base_revision': 'c' * 40, 'finding_ids_digest': 'd' * 64,
                          'path': 'producto-repair-dddddddddddddddd',
                          'branch': 'dsh/repair-dddddddddddddddd',
                          'head': head, 'status': 'DIRTY',
                          'candidate_diff_digest': diff,
                          'changed_paths': ['manage.py']},
            'items': []}, ensure_ascii=False) + '\n', encoding='utf-8')

    def write_plan(self, absent_stack=False):
        if absent_stack:
            # Stack declarado por el dueño del producto con una capability que
            # no existe: not_ready por construcción, no por esta máquina.
            (self.workspace / stack.DECLARATION_FILE).write_text(json.dumps({
                'version': stack.VERSION,
                'stacks': [{'stack': 'stack-declarado', 'root': 'sin-capability',
                            'verify': [ABSENT, 'test'],
                            'capabilities': [ABSENT]}]}, ensure_ascii=False) + '\n')
        value = stack.plan(self.workspace, workspace=self.workspace)
        stack.write(value, self.workspace)
        self.plan_value = value

    def ready_commands(self):
        return [stack._command_text(entry['verify_command'])
                for entry in stack.load(self.workspace)['stacks']
                if entry['verification_ready']]

    def write_ledger(self, *, result='PASS', diff=DIFF, finding='A-01'):
        lines = [json.dumps({'finding_id': finding, 'candidate_head': HEAD,
                             'candidate_diff_digest': diff, 'result': result,
                             'command': command}, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':')) + '\n'
                 for command in self.ready_commands()]
        path = self.state / 'verification-results.jsonl'
        path.write_text(''.join(lines), encoding='utf-8')
        return path

    def run_gate(self, fase='pre'):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            code = campaign.main(['--workspace', str(self.workspace), '--fase', fase])
        return code, stream.getvalue()

    def verdict(self):
        path = self.workspace / 'evidence' / 'veredicto.json'
        return json.loads(path.read_text(encoding='utf-8'))

    # -- veredictos

    def test_ledger_valido_da_pass(self):
        ledger = self.write_ledger()
        antes = ledger.read_bytes()
        code, output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_PASS)
        marker = [line for line in output.splitlines() if line.startswith(campaign.MARKER)]
        self.assertEqual(len(marker), 1, output)
        self.assertEqual(json.loads(marker[0].split(' ', 1)[1])['verdict'], 'PASS')
        self.assertEqual(self.verdict()['verdict'], 'PASS')
        self.assertEqual(self.verdict()['fase'], 'pre')
        self.assertEqual(self.verdict()['candidate_head'], HEAD)
        self.assertEqual(self.verdict()['candidate_diff_digest'], DIFF)
        self.assertGreaterEqual(self.verdict()['counts']['PASS'], 1)
        self.assertEqual(self.verdict()['unverified'], [])
        self.assertEqual(ledger.read_bytes(), antes)

    def test_ledger_sin_candidato_no_acredita_pass(self):
        (self.state / 'work-items.json').unlink()
        self.write_ledger()
        code, _output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertEqual(self.verdict()['verdict'], 'BLOCKED')
        self.assertIn('candidato', self.verdict()['reason'])

    def test_ledger_que_no_casa_con_la_candidata_da_fail(self):
        self.write_ledger(diff='f' * 64)
        code, output = self.run_gate('post')
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertEqual(json.loads(output.split(campaign.MARKER + ' ', 1)[1])['verdict'],
                         'FAIL')
        self.assertIn('candidato', self.verdict()['reason'])
        self.assertEqual(self.verdict()['fase'], 'post')

    def test_resultado_fail_real_da_fail(self):
        self.write_ledger(result='FAIL')
        code, _output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertEqual(self.verdict()['verdict'], 'FAIL')
        self.assertEqual(self.verdict()['counts']['FAIL'], 1)

    def test_sin_registros_no_declara_pass(self):
        code, _output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertEqual(self.verdict()['verdict'], 'BLOCKED')
        self.assertIn('sin registros', self.verdict()['reason'])

    def test_preflight_rechaza_stack_no_ready_antes_de_auditar(self):
        self.write_plan(absent_stack=True)
        from tests.test_workflow_ask import FakeAskClient
        import workflow
        client = FakeAskClient(roster=[{'id': 'campana-auditor', 'broken': False}])
        manifest = self.workspace / '.dsh-managed/campaign/manifest.json'
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text('{"preset_ids":["campana-auditor"]}\n', encoding='utf-8')
        with mock.patch('creator_client.acquire_dsh_client', return_value=(client, None)), \
             mock.patch.object(workflow, '_verify_preset', return_value=None):
            code, output = self.run_gate('preflight')
        self.assertEqual(code, campaign.EXIT_BLOCKED, output)
        self.assertIn(ABSENT, output)
        self.assertIn('stack-declarado', output)

    def test_veredicto_no_sigue_enlaces_a_fuera(self):
        outside = self.tmp / 'fuera'
        outside.mkdir()
        evidence = self.workspace / 'evidence'
        evidence.symlink_to(outside, target_is_directory=True)
        code, output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertIn('veredicto no escribible', output)
        self.assertEqual(list(outside.iterdir()), [])
        evidence.unlink()
        evidence.mkdir()
        target = outside / 'veredicto.json'
        (evidence / 'veredicto.json').symlink_to(target)
        code, output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertIn('veredicto no escribible', output)
        self.assertFalse(target.exists())

    def test_stack_sin_capability_da_blocked_nunca_fail(self):
        self.write_plan(absent_stack=True)
        self.write_ledger()
        code, output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertEqual(json.loads(output.split(campaign.MARKER + ' ', 1)[1])['verdict'],
                         'BLOCKED')
        gaps = self.verdict()['missing_capabilities']
        self.assertEqual([gap['stack'] for gap in gaps], ['stack-declarado'])
        self.assertEqual(gaps[0]['missing'], [ABSENT])

    def test_plan_de_capacidades_ilegible_da_blocked(self):
        (self.workspace / stack.PLAN_RELATIVE).unlink()
        code, output = self.run_gate('pre')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertIn('plan de capacidades',
                      json.loads(output.split(campaign.MARKER + ' ', 1)[1])['reason'])
        self.assertEqual(self.verdict()['verdict'], 'BLOCKED')

    def test_preflight_sin_cliente_da_blocked_nombrando(self):
        manifest = self.workspace / '.dsh-managed' / 'campaign'
        manifest.mkdir(parents=True)
        (manifest / 'manifest.json').write_text(json.dumps(
            {'preset_ids': ['campana-auditor', 'campana-reparacion']}) + '\n')
        import creator_client
        with mock.patch.object(creator_client, 'acquire_dsh_client',
                               return_value=(None, 'sin sesión DSH viva')):
            code, output = self.run_gate('preflight')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        reason = json.loads(output.split(campaign.MARKER + ' ', 1)[1])['reason']
        self.assertIn('sin sesión DSH viva', reason)

    def test_preflight_sin_manifiesto_da_blocked(self):
        code, output = self.run_gate('preflight')
        self.assertEqual(code, campaign.EXIT_BLOCKED)
        self.assertIn('manifiesto',
                      json.loads(output.split(campaign.MARKER + ' ', 1)[1])['reason'])

    def test_el_wrapper_no_escribe_el_ledger(self):
        ledger = self.write_ledger()
        antes = ledger.read_bytes()
        for fase in ('pre', 'post', 'final'):
            self.run_gate(fase)
        self.assertEqual(ledger.read_bytes(), antes)
        # Tampoco cuando no hay ledger: no crea el fichero que no debe escribir.
        ledger.unlink()
        self.run_gate('pre')
        self.assertFalse(ledger.exists())


class ImplementPhasesTests(unittest.TestCase):
    """Las fases Host del modo implementador: aprovisionamiento y aceptación.

    La candidata kind=implement la provisiona el Host (`mode_lifecycle.
    provision_implementation`: sombra propia, base limpia, petición exacta) y
    se registra en work-items.json para que la sesión del implementer la
    verifique y trabaje dentro de ella. La aceptación de comportamiento la
    ejecuta el Host con el entrypoint declarado del producto.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.product = self.tmp / 'product-git'
        (self.product / 'tests').mkdir(parents=True)
        (self.product / 'improvement-verification.json').write_text(
            json.dumps({'version': stack.VERSION, 'stacks': [{
                'stack': 'python-fixture', 'root': '',
                'verify': ['python3', '-B', '-m', 'unittest', 'discover',
                           '-s', 'tests'],
                'capabilities': ['python3']}]}, ensure_ascii=False) + '\n',
            encoding='utf-8')
        (self.product / 'tests' / 'test_base.py').write_text(
            'import unittest\n\n\nclass T(unittest.TestCase):\n'
            '    def test_base(self):\n        self.assertEqual(1, 1)\n',
            encoding='utf-8')
        for args in (('init', '-q'), ('-c', 'user.email=a@b', '-c', 'user.name=a',
                                      'add', '-A'), ('-c', 'user.email=a@b',
                                                     '-c', 'user.name=a', 'commit',
                                                     '-q', '-m', 'base')):
            import subprocess
            subprocess.run(['git', '-C', str(self.product), *args],
                           capture_output=True, check=True)
        self.workspace = self.tmp / 'workspace-git'
        (self.workspace / 'mode-state').mkdir(parents=True)
        value = stack.plan(self.product, workspace=self.workspace)
        stack.write(value, self.workspace)
        self.request = 'Añade un test que verifique el arranque del módulo.'

    def run_phase(self, fase):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            code = campaign.main(['--workspace', str(self.workspace),
                                  '--fase', fase, '--request', self.request])
        return code, stream.getvalue()

    def registered(self):
        return json.loads(
            (self.workspace / 'mode-state' / 'work-items.json').read_text(
                encoding='utf-8')).get('candidate')

    def test_provision_registers_the_candidate_and_creates_the_shadow(self):
        code, output = self.run_phase('provision-implement')
        self.assertEqual(code, campaign.EXIT_PASS, output[-800:])
        candidate = self.registered()
        self.assertEqual(candidate['base_revision'], candidate['head'])
        self.assertEqual(candidate['status'], 'PROVISIONED')
        shadow = self.tmp / candidate['path']
        self.assertTrue(shadow.is_dir(), 'sombra no creada')
        self.assertTrue((shadow / '.git').is_dir())
        # La candidata registrada debe cumplir el schema de estado del propio
        # módulo (el hallazgo bloqueante B1 de la revisión: la forma con
        # kind/request la rechazaba y rompía la cadena de identidad).
        import mode_lifecycle
        schema = mode_lifecycle.state_schema()
        candidate_schema = (schema['files']['work-items.json']['candidate'])
        self.assertTrue(mode_lifecycle._is_valid(candidate, candidate_schema,
                                                 'candidate'),
                        'la candidata registrada viola el schema de estado')

    def test_verify_blocks_while_the_shadow_has_no_changes(self):
        self.run_phase('provision-implement')
        code, output = self.run_phase('verificar-implement')
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertIn('no-change', output)

    def test_provision_without_request_is_blocked(self):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            code = campaign.main(['--workspace', str(self.workspace),
                                  '--fase', 'provision-implement'])
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertIn('exige --request', stream.getvalue())

    def test_provision_with_dirty_product_is_blocked(self):
        self.run_phase('provision-implement')
        # Una segunda provisión sobre candidata existente reutiliza; el camino
        # BLOCKED medido es el producto canónico sucio: ensuciamos el producto.
        (self.product / 'uncommitted.py').write_text('x = 1\n',
                                                     encoding='utf-8')
        code, output = self.run_phase('provision-implement')
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertIn('aprovisionamiento de implement', output)

    def test_verify_passes_after_an_edit_inside_the_shadow(self):
        self.run_phase('provision-implement')
        candidate = self.registered()
        shadow = self.tmp / candidate['path']
        (shadow / 'tests' / 'test_change.py').write_text(
            'import unittest\n\n\nclass Change(unittest.TestCase):\n'
            '    def test_new(self):\n        self.assertTrue(True)\n',
            encoding='utf-8')
        code, output = self.run_phase('verificar-implement')
        self.assertEqual(code, campaign.EXIT_PASS, output[-800:])
        payload = json.loads(output.split(campaign.MARKER + ' ', 1)[1])
        self.assertEqual(payload['verdict'], 'PASS')
        self.assertTrue(payload.get('candidate_diff_digest'), 'diff no medido')

    def test_verify_refuses_a_foreign_request(self):
        self.run_phase('provision-implement')
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            code = campaign.main(['--workspace', str(self.workspace),
                                  '--fase', 'verificar-implement',
                                  '--request', 'otra petición distinta'])
        self.assertEqual(code, campaign.EXIT_FAIL)
        self.assertIn('candidata/producto derivó', stream.getvalue())




if __name__ == '__main__':
    unittest.main()
