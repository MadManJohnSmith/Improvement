"""El corpus versionado es contenido publicado: saneado y estructuralmente válido.

El índice y los casos aún no existen — el ticket de corridas los versiona
(#22) — así que el gate de repo se activa en el momento en que `eval/cases/`
entra. Que un directorio ausente no se escanea no hace decoración al gate:
la prueba de unidad demuestra que los patrones cazan, y el contrato de corpus
(#19) fija que todo caso entra por revisión del mantenedor con su journal
fuera del árbol.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import creator_eval
import sanitation


class SanitationPatternsTest(unittest.TestCase):
    """Los patrones compartidos cazan cada forma antes de gatear nada real."""

    def test_each_pattern_catches_its_shape(self):
        self.assertIn("email", sanitation.violations("escríbele a a@b.org"))
        self.assertIn("credential-key",
                      sanitation.violations('{"api_key": "valor"}'))
        self.assertIn("bearer",
                      sanitation.violations("Authorization: Bearer abcdefgh1234"))
        self.assertIn("local-path",
                      sanitation.violations("lee /home/alice/proyecto"))
        self.assertIn("postal-address",
                      sanitation.violations("vive en calle Mayor 12"))

    def test_clean_content_has_no_violations(self):
        self.assertEqual(
            sanitation.violations("digest df270183, usage 1.409.291, "
                                  "veredicto FAIL_COMPLETION"),
            [],
            "los falsos positivos son defectos del gate, no ruido aceptable")


class EvalCasesGateTest(unittest.TestCase):
    def test_versioned_cases_are_sanitized_and_the_index_is_valid(self):
        cases = ROOT / "eval" / "cases"
        if not cases.is_dir():
            # El corpus aún no está versionado (#22): la ausencia es el estado
            # esperado y se afirma; el gate se activa solo cuando entra.
            self.assertFalse((cases / "index.json").exists(),
                             "índice sin directorio de casos")
            return
        found = []
        for path in sorted(cases.rglob("*")):
            if path.is_file():
                hits = sanitation.violations(
                    path.read_text(encoding="utf-8", errors="replace"))
                if hits:
                    found.append(f"{path.name}: {', '.join(hits)}")
        self.assertEqual(
            found, [],
            "un caso versionado lleva hechos derivados, no datos de persona "
            "ni rutas de máquina ni credenciales")
        index = cases / "index.json"
        if index.is_file():
            creator_eval.validate_index(index)


class VersionedCaseCriteriaTests(unittest.TestCase):
    """Los criteria por caso versionado pasan por el validador del evaluador.

    El índice se valida y los facts llevan su puerta de saneamiento, pero un
    `criteria.json` malformado solo se descubría en la corrida externa —
    cara y posterior al despacho—, nunca en la suite. La misma función que
    exige el evaluador al gradear (`require_criteria`) decide aquí, offline
    y sin gastar.
    """

    def test_every_versioned_case_criteria_passes_the_evaluator_validator(self):
        import json

        cases = ROOT / "eval" / "cases"
        checked = 0
        for path in sorted(cases.glob("*/criteria.json")):
            with self.subTest(case=path.parent.name):
                criteria = json.loads(path.read_text(encoding="utf-8"))
                creator_eval.require_criteria(criteria)
            checked += 1
        self.assertTrue(
            checked,
            "sin criteria versionados que validar: el escaneo está roto")


if __name__ == "__main__":
    unittest.main()
