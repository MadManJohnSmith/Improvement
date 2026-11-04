"""Regression for the doc-drift DSH plugin (ADR 0002).

Offline: `verify-doc-drift.mjs` drives the plugin's deterministic logic with a
mock ctx and the real engine (`scripts/drift.py`) against a synthetic git
repository created in a temporary directory. The live DSH event shapes are
exercised by the DSH-dependent suite, not here.

    python3 -B -m unittest tests.test_doc_drift_plugin -v
"""
import shutil
import subprocess
import unittest
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
VERIFIER = FRAMEWORK / 'scripts' / 'dsh-plugins' / 'verify-doc-drift.mjs'


class DocDriftPluginTest(unittest.TestCase):
    def test_the_offline_verifier_passes(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node no disponible')
        proc = subprocess.run([node, str(VERIFIER)], capture_output=True,
                              text=True, timeout=600, check=False)
        if proc.returncode == 3:
            self.skipTest(proc.stdout.strip() or 'verificador sin prerequisitos')
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn('FAIL', proc.stdout)
        self.assertIn('OK: verificador de doc-drift en verde', proc.stdout)
