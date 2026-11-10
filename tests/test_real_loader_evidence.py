"""La evidencia contra el loader real corre programada, no solo a mano.

`tests/test_dsh_frontmatter_shape.mjs` y `tests/test_dsh_skill_root.mjs`
miden el loader real de DSH —el defecto de quoting que la suite Python fija
por contrato nació de esa medición— y
`scripts/dsh-plugins/verify-doc-drift.mjs` autochequea el plugin de drift
offline. Los dos primeros solo vivían en `docs/setup-dsh.md`: sin alguien
ejecutándolos a mano, un cambio del loader real se enteraba tarde. Aquí
corren con la convención de la suite: skip que nombra el componente
ausente, salida 0 cuando están.
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class OfflineDriftSelfcheckTests(unittest.TestCase):
    def test_the_doc_drift_plugin_selfcheck_passes_with_node(self):
        if NODE is None:
            self.skipTest("node")
        outcome = subprocess.run(
            [NODE, "scripts/dsh-plugins/verify-doc-drift.mjs"],
            cwd=str(REPO_ROOT), capture_output=True, text=True)
        self.assertEqual(outcome.returncode, 0,
                         outcome.stdout + outcome.stderr)


class RealLoaderEvidenceTests(unittest.TestCase):
    def setUp(self):
        if NODE is None:
            self.skipTest("node")
        if not os.environ.get("DSH_MODULE_ROOT"):
            self.skipTest("DSH_MODULE_ROOT")

    def test_the_real_loader_checks_pass_against_the_installed_runtime(self):
        for script in ("tests/test_dsh_frontmatter_shape.mjs",
                       "tests/test_dsh_skill_root.mjs"):
            with self.subTest(script=script):
                outcome = subprocess.run(
                    [NODE, script], cwd=str(REPO_ROOT),
                    capture_output=True, text=True)
                self.assertEqual(outcome.returncode, 0,
                                 outcome.stdout + outcome.stderr)


if __name__ == "__main__":
    unittest.main()
