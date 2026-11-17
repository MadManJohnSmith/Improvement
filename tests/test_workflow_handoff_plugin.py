"""Regresión offline del gate de handoffs del plugin workflow-write (issue #38).

Offline: `verify-workflow-handoff.mjs` invoca la tool REAL `workflow_write`
con un ctx simulado y un mode-state de fixture en un directorio temporal — el
mismo patrón que `verify-doc-drift.mjs`. Las formas vivas de DSH las ejercita
la suite dependiente de DSH, no aquí.

    python3 -B -m unittest tests.test_workflow_handoff_plugin -v
"""
import shutil
import subprocess
import unittest
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
VERIFIER = FRAMEWORK / 'scripts' / 'dsh-plugins' / 'verify-workflow-handoff.mjs'


class WorkflowHandoffPluginTest(unittest.TestCase):
    def test_el_verificador_offline_pasa(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node no disponible')
        proc = subprocess.run([node, str(VERIFIER)], capture_output=True,
                              text=True, timeout=600, check=False)
        if proc.returncode == 3:
            self.skipTest(proc.stdout.strip() or 'verificador sin prerequisitos')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn('FAIL', proc.stdout)
        self.assertIn('OK: verificador de handoffs de auditoría en verde', proc.stdout)


if __name__ == '__main__':
    unittest.main()
