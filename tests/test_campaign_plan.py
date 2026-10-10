"""Regresiones del generador de campaña (U6b): determinismo byte a byte, los
ocho pasos del plan por defecto y su derivación con rondas, un plan que
`workflow.load_plan` acepta sin transformarlo, y el manifiesto que ata el plan a
su sha256. Todo el trabajo ocurre en /tmp."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest

from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import campaign_plan
import workflow

from campaign_plan import CampaignPlanError

# Ids tal y como los publica la instalación: verificados, en orden de emisión.
PRESETS = ['campana-auditor', 'campana-reparacion', 'campana-cierre']
PYTHON = shutil.which('python3')


class CampaignPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'producto'
        self.workspace.mkdir()
        self.stack_value = {'stacks': []}

    def generate(self, presets=None, **kwargs):
        return campaign_plan.generate(self.workspace, self.stack_value,
                                      presets or PRESETS, **kwargs)

    def steps_by_id(self, bundle):
        return {step['id']: step for step in bundle['plan']['steps']}

    def test_regeneracion_producece_bytes_identicos(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(first['plan_bytes'], second['plan_bytes'])
        self.assertEqual(first['manifest_bytes'], second['manifest_bytes'])
        self.assertEqual(first['prompts'], second['prompts'])
        # Y el fichero en disco tampoco cambia entre generaciones seguidas.
        campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        first_on_disk = (self.workspace / campaign_plan.CAMPAIGN_RELATIVE /
                         campaign_plan.PLAN_NAME).read_bytes()
        campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertEqual(
            (self.workspace / campaign_plan.CAMPAIGN_RELATIVE /
             campaign_plan.PLAN_NAME).read_bytes(), first_on_disk)

    def test_write_campaign_idempotente_preserva_mtime_y_devuelve_recibo(self):
        first = campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertTrue(first['written'])
        path = Path(first['path'])
        self.assertTrue(path.is_absolute())
        self.assertEqual(path, self.workspace / '.dsh-managed/campaign/plan.json')
        files = [path, path.with_name('manifest.json'),
                 path.parent / 'prompts/auditar.md',
                 path.parent / 'prompts/reparar.md']
        before = {file: (file.stat().st_mtime_ns, file.read_bytes()) for file in files}
        second = campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertFalse(second['written'])
        self.assertEqual(first['campaign_plan_sha256'], second['campaign_plan_sha256'])
        self.assertEqual(before, {file: (file.stat().st_mtime_ns, file.read_bytes())
                                  for file in files})
        plan = json.loads(path.read_bytes())
        for step in plan['steps']:
            if step['type'] == 'gate':
                self.assertTrue(Path(step['command'][0]).is_absolute())
                self.assertTrue(Path(step['command'][1]).is_absolute())
        self.assertEqual(json.loads(files[1].read_bytes())['campaign_plan_sha256'],
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_write_campaign_rechaza_symlink_sin_escribir_fuera(self):
        outside = self.tmp / 'fuera'
        outside.mkdir()
        managed = self.workspace / '.dsh-managed'
        managed.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertEqual(list(outside.iterdir()), [])
        managed.unlink()
        campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        target = self.workspace / '.dsh-managed/campaign/plan.json'
        target.unlink()
        external = outside / 'plan.json'
        target.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertFalse(external.exists())
        target.unlink()
        prompts = self.workspace / '.dsh-managed/campaign/prompts'
        shutil.rmtree(prompts)
        prompts.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        self.assertFalse((outside / 'auditar.md').exists())

    def test_gate_retiene_si_campaign_o_interprete_cambian_antes_de_ejecutar(self):
        from tests.test_workflow_ask import FakeAskClient
        for changed in ('script', 'python'):
            with self.subTest(changed=changed):
                workspace = self.tmp / ('producto-' + changed)
                workspace.mkdir()
                managed = workspace / '.dsh-managed/campaign'
                (managed / 'prompts').mkdir(parents=True)
                interpreter = self.tmp / ('python-' + changed)
                script = self.tmp / ('campaign-' + changed + '.py')
                shutil.copy2(PYTHON, interpreter)
                script.write_text('from pathlib import Path\n'
                                  'Path(%r).write_text("ejecutado")\n' %
                                  str(self.tmp / ('executed-' + changed)), encoding='utf-8')
                bundle = campaign_plan.generate(
                    workspace, self.stack_value, PRESETS,
                    python=str(interpreter), script=str(script))
                (managed / 'plan.json').write_bytes(bundle['plan_bytes'])
                (managed / 'manifest.json').write_bytes(bundle['manifest_bytes'])
                for name, data in bundle['prompts'].items():
                    (managed / 'prompts' / name).write_bytes(data)
                if changed == 'script':
                    script.write_text('raise RuntimeError("otro binario")\n', encoding='utf-8')
                else:
                    interpreter.unlink()
                result = workflow.run_plan(managed / 'plan.json',
                                           ask_client=FakeAskClient(roster=[
                                               {'id': preset, 'broken': False}
                                               for preset in PRESETS]))
                self.assertEqual(result['result'], 'RETAINED')
                self.assertIn('campaign-regeneracion-requerida:preflight', result['cause'])
                self.assertFalse((self.tmp / ('executed-' + changed)).exists())
                journal = workflow.read_journal(result['run_dir'])
                self.assertFalse(any(event['kind'] == 'STEP_STARTED' for event in journal))

    def test_gate_real_preflight_importa_modulos_hermanos_desde_memfd(self):
        workspace = self.tmp / 'producto-real'
        workspace.mkdir()
        managed = workspace / '.dsh-managed/campaign'
        (managed / 'prompts').mkdir(parents=True)
        bundle = campaign_plan.generate(workspace, self.stack_value, PRESETS)
        (managed / 'plan.json').write_bytes(bundle['plan_bytes'])
        (managed / 'manifest.json').write_bytes(bundle['manifest_bytes'])
        for name, data in bundle['prompts'].items():
            (managed / 'prompts' / name).write_bytes(data)
        from tests.test_workflow_ask import FakeAskClient
        result = workflow.run_plan(managed / 'plan.json',
                                   ask_client=FakeAskClient(roster=[
                                       {'id': preset, 'broken': False} for preset in PRESETS]))
        self.assertEqual(result['result'], 'RETAINED')
        observations = list((Path(result['run_dir']) / 'observations').glob('*-preflight-gate.json'))
        self.assertEqual(len(observations), 1)
        stderr = json.loads(observations[0].read_bytes())['stderr']
        self.assertNotIn('ModuleNotFoundError', stderr)
        self.assertNotIn('Traceback', stderr)
        self.assertIn('BLOCKED', stderr)

    def test_gate_ejecuta_bytes_sellados_si_interprete_cambia_en_dispatch(self):
        from tests.test_workflow_ask import FakeAskClient
        workspace = self.tmp / 'producto-python-swap'
        workspace.mkdir()
        managed = workspace / '.dsh-managed/campaign'
        (managed / 'prompts').mkdir(parents=True)
        interpreter = self.tmp / 'python-replaced'
        script = self.tmp / 'campaign-python-swap.py'
        shutil.copy2(PYTHON, interpreter)
        script.write_text('import sys\nsys.exit(2)\n', encoding='utf-8')
        bundle = campaign_plan.generate(workspace, self.stack_value, PRESETS,
                                        python=str(interpreter), script=str(script))
        (managed / 'plan.json').write_bytes(bundle['plan_bytes'])
        (managed / 'manifest.json').write_bytes(bundle['manifest_bytes'])
        for name, data in bundle['prompts'].items():
            (managed / 'prompts' / name).write_bytes(data)
        real_run = workflow.subprocess.run

        def swap_at_dispatch(command, **kwargs):
            interpreter.unlink()
            interpreter.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            interpreter.chmod(0o700)
            return real_run(command, **kwargs)

        with mock.patch.object(workflow.subprocess, 'run', side_effect=swap_at_dispatch):
            result = workflow.run_plan(managed / 'plan.json',
                                       ask_client=FakeAskClient(roster=[
                                           {'id': preset, 'broken': False}
                                           for preset in PRESETS]))
        self.assertEqual(result['result'], 'RETAINED')
        self.assertEqual(result['cause'], 'gate-impossible:preflight:exit=2')

    def test_gate_ejecuta_bytes_sellados_si_el_script_se_sustituye_en_dispatch(self):
        from tests.test_workflow_ask import FakeAskClient
        workspace = self.tmp / 'producto-swap'
        workspace.mkdir()
        managed = workspace / '.dsh-managed/campaign'
        (managed / 'prompts').mkdir(parents=True)
        interpreter = self.tmp / 'python-swap'
        script = self.tmp / 'campaign-swap.py'
        shutil.copy2(PYTHON, interpreter)
        proof = self.tmp / 'swapped-script-executed'
        script.write_text('import sys\nsys.exit(2)\n', encoding='utf-8')
        bundle = campaign_plan.generate(workspace, self.stack_value, PRESETS,
                                        python=str(interpreter), script=str(script))
        (managed / 'plan.json').write_bytes(bundle['plan_bytes'])
        (managed / 'manifest.json').write_bytes(bundle['manifest_bytes'])
        for name, data in bundle['prompts'].items():
            (managed / 'prompts' / name).write_bytes(data)
        real_run = workflow.subprocess.run

        def swap_at_dispatch(command, **kwargs):
            script.write_text('from pathlib import Path\nPath(%r).write_text("ran")\n' %
                              str(proof), encoding='utf-8')
            return real_run(command, **kwargs)

        with mock.patch.object(workflow.subprocess, 'run', side_effect=swap_at_dispatch):
            result = workflow.run_plan(managed / 'plan.json',
                                       ask_client=FakeAskClient(roster=[
                                           {'id': preset, 'broken': False}
                                           for preset in PRESETS]))
        self.assertEqual(result['result'], 'RETAINED')
        self.assertFalse(proof.exists(), 'los bytes sustituidos no pueden ejecutarse')
        self.assertEqual(result['cause'], 'gate-impossible:preflight:exit=2')
        journal = workflow.read_journal(result['run_dir'])
        self.assertTrue(any(event['kind'] == 'STEP_STARTED' for event in journal))
        observations = list((Path(result['run_dir']) / 'observations').glob('*-preflight-gate.json'))
        self.assertEqual(len(observations), 1)
        self.assertEqual(json.loads(observations[0].read_bytes())['exit_code'], 2)

        with self.subTest(case='modulo_first_party_sustituido_en_dispatch'):
            workspace_m = self.tmp / 'producto-mod-swap'
            workspace_m.mkdir()
            managed_m = workspace_m / '.dsh-managed/campaign'
            (managed_m / 'prompts').mkdir(parents=True)
            mod_dir = self.tmp / 'scripts-swap'
            mod_dir.mkdir()
            for f in (Path(REPO_ROOT / 'scripts').glob('*.py')):
                (mod_dir / f.name).write_bytes(f.read_bytes())
            proof_m = self.tmp / 'swapped-module-executed'
            helper = mod_dir / 'module_swap_target.py'
            helper.write_text('def run(): return "original"\n', encoding='utf-8')
            script_m = mod_dir / 'campaign-mod-swap.py'
            script_m.write_text(
                'import module_swap_target, sys\n'
                'val = module_swap_target.run()\n'
                'if val == "tampered":\n'
                '    from pathlib import Path\n'
                '    Path(%r).write_text("ran")\n'
                'sys.exit(2)\n' % str(proof_m), encoding='utf-8')
            bundle_m = campaign_plan.generate(workspace_m, self.stack_value, PRESETS,
                                              python=PYTHON, script=str(script_m))
            (managed_m / 'plan.json').write_bytes(bundle_m['plan_bytes'])
            (managed_m / 'manifest.json').write_bytes(bundle_m['manifest_bytes'])
            for name, data in bundle_m['prompts'].items():
                (managed_m / 'prompts' / name).write_bytes(data)

            def swap_mod_at_dispatch(command, **kwargs):
                helper.write_text('def run(): return "tampered"\n', encoding='utf-8')
                return real_run(command, **kwargs)

            with mock.patch.object(workflow.subprocess, 'run', side_effect=swap_mod_at_dispatch):
                res_m = workflow.run_plan(managed_m / 'plan.json',
                                          ask_client=FakeAskClient(roster=[
                                              {'id': preset, 'broken': False}
                                              for preset in PRESETS]))
            self.assertEqual(res_m['result'], 'RETAINED')
            self.assertFalse(proof_m.exists(), 'el módulo sustituido en disco no debe ejecutarse')
            self.assertEqual(res_m['cause'], 'gate-impossible:preflight:exit=2')

            # Sustitución antes de arrancar el runner:
            helper.write_text('def run(): return "modified_before_run"\n', encoding='utf-8')
            res_m2 = workflow.run_plan(managed_m / 'plan.json',
                                       ask_client=FakeAskClient(roster=[
                                           {'id': preset, 'broken': False}
                                           for preset in PRESETS]))
            self.assertEqual(res_m2['result'], 'RETAINED')
            self.assertIn('campaign-regeneracion-requerida:preflight', res_m2['cause'])

    def test_plan_por_defecto_tiene_ocho_pasos_con_su_tipo_y_on_fail(self):
        bundle = self.generate()
        steps = bundle['plan']['steps']
        self.assertEqual([step['id'] for step in steps],
                         ['preflight', 'auditar', 'verificar-pre', 'reparar-1',
                          'verificar-post', 'reparar-2', 'verificar-final', 'cerrar'])
        self.assertEqual(bundle['plan']['name'], 'campana-producto')
        self.assertEqual(bundle['plan']['workspace'], str(self.workspace.resolve()))
        self.assertEqual(bundle['plan']['preset'], PRESETS[0])
        for step in steps:
            self.assertEqual(step.get('depends', []), [], step['id'])
        by_id = self.steps_by_id(bundle)
        self.assertEqual(by_id['preflight']['type'], 'gate')
        self.assertEqual(by_id['preflight']['on_fail'], {'action': 'abort', 'rounds': 1})
        self.assertEqual(by_id['verificar-pre']['on_fail'], {'action': 'continue', 'rounds': 1})
        self.assertEqual(by_id['verificar-post']['on_fail'], {'action': 'continue', 'rounds': 1})
        self.assertEqual(by_id['verificar-final']['on_fail'], {'action': 'abort', 'rounds': 1})
        self.assertEqual(by_id['cerrar']['on_fail'], {'action': 'abort', 'rounds': 1})
        for phase in ('preflight', 'pre', 'post', 'final', 'cerrar'):
            commands = [step['command'] for step in steps
                        if step['type'] == 'gate' and phase in step['command']]
            self.assertEqual(len(commands), 1, phase)
            self.assertEqual(commands[0][-1], phase)
            self.assertTrue(commands[0][1].endswith('campaign.py'))
        self.assertEqual(by_id['auditar']['type'], 'ask')
        self.assertEqual(by_id['auditar']['preset'], 'campana-auditor')
        self.assertEqual(by_id['auditar']['prompt_file'], 'prompts/auditar.md')
        self.assertEqual(by_id['auditar']['result_contract'],
                         {'path': 'auditoria.json', 'evidence_name': 'campana'})
        self.assertEqual(by_id['reparar-1']['preset'], 'campana-reparacion')
        self.assertEqual(by_id['reparar-1']['prompt_file'], 'prompts/reparar.md')
        self.assertEqual(by_id['reparar-1']['if_veredicto'],
                         {'from': 'verificar-pre', 'path': 'veredicto.json',
                          'field': 'verdict', 'equals': 'FAIL'})
        self.assertEqual(by_id['reparar-2']['if_veredicto']['from'], 'verificar-post')
        self.assertEqual(by_id['reparar-1']['result_contract'],
                         {'path': 'reparar.json', 'evidence_name': 'campana'})

        with self.subTest(case='plan_generado_fail_continue_crea_sesion_y_pass_posterior_no_reescribe'):
            from tests.test_workflow_ask import FakeAskClient
            workspace_f = self.tmp / 'producto-campana-flujo'
            workspace_f.mkdir()
            managed_f = workspace_f / '.dsh-managed/campaign'
            (managed_f / 'prompts').mkdir(parents=True)
            mod_dir_f = self.tmp / 'scripts-campana-flujo'
            mod_dir_f.mkdir()
            for f in (Path(REPO_ROOT / 'scripts').glob('*.py')):
                (mod_dir_f / f.name).write_bytes(f.read_bytes())
            script_f = mod_dir_f / 'campaign_flow_test.py'
            script_f.write_text('''
import argparse, json, sys, pathlib
import campaign

parser = argparse.ArgumentParser()
parser.add_argument('--workspace', required=True)
parser.add_argument('--fase', required=True)
args = parser.parse_args()

ws = pathlib.Path(args.workspace)
if args.fase == 'preflight':
    sys.exit(0)
elif args.fase == 'pre':
    campaign.write_verdict(ws, {'fase': 'pre', 'verdict': 'FAIL', 'counts': {'FAIL': 1}, 'records': 1, 'usable': 1})
    sys.exit(1)
elif args.fase == 'post':
    campaign.write_verdict(ws, {'fase': 'post', 'verdict': 'PASS', 'counts': {'PASS': 1}, 'records': 1, 'usable': 1})
    sys.exit(0)
elif args.fase in ('final', 'cerrar'):
    sys.exit(0)
''', encoding='utf-8')
            bundle_f = campaign_plan.generate(workspace_f, self.stack_value, PRESETS,
                                              python=PYTHON, script=str(script_f))
            (managed_f / 'plan.json').write_bytes(bundle_f['plan_bytes'])
            (managed_f / 'manifest.json').write_bytes(bundle_f['manifest_bytes'])
            for name, data in bundle_f['prompts'].items():
                (managed_f / 'prompts' / name).write_bytes(data)

            client_f = FakeAskClient(roster=[{'id': preset, 'broken': False} for preset in PRESETS])
            client_f.auto_complete_on_send = True

            def on_complete(session):
                ws = session.workspace
                camp = ws / 'evidence' / 'campana'
                camp.mkdir(parents=True, exist_ok=True)
                if not (camp / 'auditoria.json').exists():
                    (camp / 'auditoria.json').write_text(json.dumps({'audit': 'done'}), encoding='utf-8')
                else:
                    (camp / 'reparar.json').write_text(json.dumps({'repair': 'done'}), encoding='utf-8')

            client_f.on_complete = on_complete

            # 1. Ejecutar plan generado
            outcome_f = workflow.run_plan(managed_f / 'plan.json', ask_client=client_f)
            self.assertEqual(outcome_f['result'], 'COMPLETED')
            # auditar (1) y reparar-1 (2) deben haber creado sesión; reparar-2 debe haberse saltado
            self.assertEqual(len(client_f.created), 2)
            sessions = [c[2] for c in client_f.created]
            self.assertIn('campana-auditor', sessions[0])
            self.assertIn('campana-reparacion', sessions[1])

            events_f = workflow.read_journal(outcome_f['run_dir'])
            skipped_f = [e['payload'] for e in events_f if e['kind'] == 'ASK_SKIPPED']
            self.assertEqual(len(skipped_f), 1)
            self.assertEqual(skipped_f[0]['step_id'], 'reparar-2')
            self.assertEqual(skipped_f[0]['from'], 'verificar-post')
            self.assertEqual(skipped_f[0]['real'], 'PASS')
            self.assertEqual(skipped_f[0]['esperado'], 'FAIL')

            # 2. Replay y verificación inmutables:
            # El posterior PASS en verificar-post no sobreescribe ni invalida reparar-1
            self.assertEqual(workflow.verify(outcome_f['run_dir'])['events'], len(events_f))
            resumed_f = workflow.run_plan(managed_f / 'plan.json', ask_client=client_f)
            self.assertEqual(resumed_f['result'], 'COMPLETED')
            self.assertEqual(len(client_f.created), 2)

    def test_rondas_max_tres_emite_tres_pares(self):
        bundle = self.generate(rondas_max=3)
        steps = bundle['plan']['steps']
        self.assertEqual([step['id'] for step in steps],
                         ['preflight', 'auditar', 'verificar-pre', 'reparar-1',
                          'verificar-post', 'reparar-2', 'verificar-ronda-3', 'reparar-3',
                          'verificar-final', 'cerrar'])
        by_id = self.steps_by_id(bundle)
        for index, label in ((1, 'verificar-pre'), (2, 'verificar-post'),
                             (3, 'verificar-ronda-3')):
            step = by_id['reparar-%d' % index]
            self.assertEqual(step['if_veredicto']['from'], label)
            self.assertEqual(step['preset'], 'campana-reparacion')
        # El número de rondas vive en el generador, no en el plan: el plan dice
        # cuántos pasos tiene, y el manifiesto dice cuántas rondas se pidieron.
        self.assertEqual(bundle['manifest']['rondas_max'], 3)
        self.assertEqual(len(steps), 2 + 2 * 3 + 2)

    def test_plan_aceptado_por_load_plan_sin_cambios(self):
        campaign_plan.write_campaign(self.workspace, self.stack_value, PRESETS)
        plan_path = Path(self.workspace / campaign_plan.CAMPAIGN_RELATIVE /
                         campaign_plan.PLAN_NAME)
        plan, raw = workflow.load_plan(plan_path)
        self.assertEqual(len(plan['steps']), 8)
        self.assertEqual(plan['name'], 'campana-producto')
        self.assertEqual(plan['preset'], PRESETS[0])
        self.assertEqual([step['type'] for step in plan['steps']],
                         ['gate', 'ask', 'gate', 'ask', 'gate', 'ask', 'gate', 'gate'])
        # El prompt_file se resolvió desde el directorio del plan, sin tocarlo.
        self.assertTrue(plan['steps'][1]['prompt'].startswith('# Auditar'))
        self.assertEqual(raw, plan_path.read_bytes())

    def test_manifest_ata_el_plan_a_su_sha256(self):
        bundle = self.generate()
        manifest = bundle['manifest']
        self.assertEqual(manifest['campaign_plan_sha256'],
                         hashlib.sha256(bundle['plan_bytes']).hexdigest())
        self.assertEqual(manifest['preset_ids'], PRESETS)
        self.assertEqual(manifest['rondas_max'], campaign_plan.ROUNDS_DEFAULT)
        self.assertEqual(manifest['generation'],
                         'campana-' + manifest['campaign_plan_sha256'][:16])
        self.assertEqual(manifest['stacks'], [])
        self.assertEqual(json.loads(bundle['manifest_bytes'])['campaign_plan_sha256'],
                         manifest['campaign_plan_sha256'])

    def test_preset_ids_vienen_de_la_lista_recibida(self):
        presets = ['cierre-extra', 'otro-auditor', 'plan-reparar']
        bundle = self.generate(presets=presets)
        by_id = self.steps_by_id(bundle)
        self.assertEqual(bundle['plan']['preset'], 'cierre-extra')
        self.assertEqual(by_id['auditar']['preset'], 'otro-auditor')
        self.assertEqual(by_id['reparar-1']['preset'], 'plan-reparar')
        self.assertEqual(bundle['manifest']['preset_ids'], presets)
        # Sin preset que nombre un rol, nada se escribe: el preflight se
        # abstendría más tarde, y un plan escrito así engaña al operador.
        with self.assertRaisesRegex(CampaignPlanError, 'auditor'):
            self.generate(presets=['solo-cierre'])
        with self.assertRaisesRegex(CampaignPlanError, 'reparación'):
            self.generate(presets=['solo-auditor'])
        self.assertFalse((self.workspace / campaign_plan.CAMPAIGN_RELATIVE).exists())


if __name__ == '__main__':
    unittest.main()