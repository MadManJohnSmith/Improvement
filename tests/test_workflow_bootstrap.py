"""Pruebas de la entrada bootstrap del ejecutor de workflow (U2): subcomando
`workflow run|verify`, resolución de run_root y abstención real ante plan con
ask sin cliente DSH. La adquisición usa la vía no-launch y en los tests se
neutraliza por completo (DSH_HOME temporal vacío y DSH_HOME_CANDIDATES a
candidatos vacíos): jamás se toca el ~/.dsh real ([corr-1] — fijar solo
DSH_HOME no basta, acquire itera también ~/.dsh, ~/.deepseek y ~/.config/dsh)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import bootstrap
import creator_client

# shutil.which('python3') y no sys.executable: en este host sys.executable es
# el AppImage de ZCode, que arranca una GUI (convención de test_metrics.py).
PYTHON = shutil.which('python3')
BOOTSTRAP = REPO_ROOT / 'scripts' / 'bootstrap.py'


class WorkflowBootstrapTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'

    def write_plan(self, steps, *, filename='plan.json'):
        plan = {'schema_version': 1, 'name': 'prueba', 'workspace': str(self.workspace),
                'steps': steps}
        path = self.tmp / filename
        path.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':')) + '\n', encoding='utf-8')
        return path

    @staticmethod
    def gate(step_id, command, action='abort', rounds=1):
        return {'id': step_id, 'type': 'gate', 'command': command,
                'on_fail': {'action': action, 'rounds': rounds}}

    def cli(self, *args):
        return subprocess.run([PYTHON, '-B', str(BOOTSTRAP), 'workflow', *args],
                              cwd=str(REPO_ROOT), capture_output=True, text=True,
                              timeout=120,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def entry(self, *args):
        """Invoca bootstrap.main in-process con el entorno DSH neutralizado."""
        dsh_home = self.tmp / 'dsh-home'
        dsh_home.mkdir()  # DSH_HOME temporal vacío: nunca el ~/.dsh real.
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ['bootstrap.py', 'workflow', *args]
        with mock.patch.object(creator_client, 'DSH_HOME_CANDIDATES', ()), \
             mock.patch.dict(os.environ, {'DSH_HOME': str(dsh_home)}), \
             mock.patch.object(sys, 'argv', argv), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                bootstrap.main()
                code = 0
            except SystemExit as failure:
                code = failure.code if isinstance(failure.code, int) else 1
        return code, stdout.getvalue(), stderr.getvalue()

    # -- plan gate-only vía bootstrap: JSON a stdout y exit 0

    def test_plan_gate_only_por_bootstrap_run_completed(self):
        plan_path = self.write_plan([self.gate('g1', ['true'])])
        proc = self.cli('run', str(plan_path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        emitted = json.loads(proc.stdout)
        self.assertEqual(emitted['result'], 'COMPLETED')
        run_dir = Path(emitted['run_dir'])
        self.assertEqual(run_dir.parent, self.run_root,
                         'por defecto el run dir es el hermano externo')
        self.assertTrue((run_dir / 'journal.jsonl').is_file())

        verified = self.cli('verify', str(run_dir))
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout)['result'], 'VERIFIED')

    # -- --run-root sobreescribe el hermano externo por defecto

    def test_run_root_override_por_bootstrap(self):
        override = self.tmp / 'raiz-alternativa'
        plan_path = self.write_plan([self.gate('g1', ['true'])])
        proc = self.cli('run', str(plan_path), '--run-root', str(override))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        emitted = json.loads(proc.stdout)
        self.assertEqual(Path(emitted['run_dir']).parent, override)
        self.assertTrue(override.is_dir())
        self.assertFalse(self.run_root.exists(), 'el hermano por defecto no se crea')

    # -- plan con ask y sin cliente DSH: ABSTAINED a stderr, exit 1, sin run dir

    def test_plan_con_ask_sin_cliente_dsh_abstiene(self):
        plan_path = self.write_plan([self.gate('g1', ['true']),
                                     {'id': 'a1', 'type': 'ask', 'prompt': 'resume'}])
        code, out, err = self.entry('run', str(plan_path))
        self.assertEqual(code, 1)
        self.assertEqual(out, '', 'la abstención no emite resultado a stdout')
        emitted = json.loads(err)
        self.assertEqual(emitted['result'], 'ABSTAINED')
        self.assertIn('ask', emitted['reason'])
        self.assertIn('DSH', emitted['reason'])
        dsh_home = str(self.tmp / 'dsh-home')
        self.assertIn(dsh_home, emitted['reason'],
                      'la pieza que falta se nombra con el home temporal probado')
        self.assertNotIn('~/.dsh', emitted['reason'])
        self.assertNotIn(str(Path.home()), emitted['reason'],
                         'ningún candidato real del host aparece en la prueba')
        self.assertFalse(self.run_root.exists(), 'sin run dir ni journal')

    # -- plan inexistente: {"error"} a stderr y exit 1

    def test_plan_inexistente_error_json(self):
        proc = self.cli('run', str(self.tmp / 'no-existe.json'))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, '')
        emitted = json.loads(proc.stderr)
        self.assertIn('error', emitted)
        self.assertIn('plan ilegible', emitted['error'])
        self.assertFalse(self.run_root.exists())

    # -- RETAINED es comando-decisión: resultado a stdout y exit 1

    def test_retained_por_bootstrap_es_comando_decision(self):
        plan_path = self.write_plan([self.gate('g1', ['false'])])
        proc = self.cli('run', str(plan_path))
        self.assertEqual(proc.returncode, 1)
        emitted = json.loads(proc.stdout)
        self.assertEqual(emitted['result'], 'RETAINED')
        self.assertEqual(emitted['cause'], 'gate-abort:g1')
        self.assertEqual(json.loads(Path(emitted['run_dir'], 'journal.jsonl').read_bytes()
                                    .decode('utf-8').splitlines()[-1])['kind'],
                         'RUN_RETAINED')


if __name__ == '__main__':
    unittest.main()
