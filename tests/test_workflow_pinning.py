"""Cada acción de los workflows va anclada por SHA completo.

Una referencia por tag (`@v4`) es mutable: el contenido que apunta puede
cambiar sin que este repo se entere, y el workflow de evaluación maneja un
secreto (`DSH_PROVIDER_API_KEY`). El pin de 40 hex hace auditable el
abastecimiento de las únicas dependencias externas que este repo ejecuta.
`actionlint` ya valida la sintaxis en CI; este canary exige el ancla.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"@[0-9a-f]{40}\b")


class WorkflowActionPinningTests(unittest.TestCase):
    def test_every_action_reference_is_pinned_to_a_full_sha(self):
        workflows = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(workflows, "escaneo roto: no hay workflows")
        for path in workflows:
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if "uses:" not in line:
                    continue
                reference = line.split("uses:", 1)[1].strip()
                with self.subTest(workflow=path.name, line=number):
                    self.assertRegex(
                        reference, FULL_SHA,
                        "acción anclada por tag (referencia mutable): fija "
                        "el SHA completo del commit y anota la versión")


if __name__ == "__main__":
    unittest.main()
