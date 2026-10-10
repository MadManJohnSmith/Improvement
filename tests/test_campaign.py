"""Regresiones del gate de campaña (U6b): PASS con ledger vivo, FAIL cuando el
registro no casa con la candidata vigente, BLOCKED cuando falta una capability o
el plan de capacidades es ilegible, abstención del preflight sin cliente DSH, y
la garantía de que el wrapper nunca escribe el ledger de verificación. Todo el
trabajo ocurre en /tmp."""
import contextlib
import io
import json
import sys
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


if __name__ == '__main__':
    unittest.main()