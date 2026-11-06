"""El caso remoto de Creator se pre-registra con artefactos versionados, no con ficheros escritos a mano en la máquina del mantenedor.

`eval/` publica los dos artefactos de configuración del caso remoto: el
criterio que `scripts/creator_eval.py` consume (el mismo triple que
`_require_criteria` exigía a los casos escritos a mano, más el `id` que llega
al reporte) y la plantilla del perfil de DSH que el workflow rellena desde
variables y secretos. Esta prueba es su contrato: si el criterio deja de ser
consumible o la plantilla fija una clave, un proveedor o una máquina local,
la suite lo detecta antes de que el workflow gaste tokens.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
sys.path.insert(0, str(ROOT / "scripts"))

import creator_eval


CRITERIA_PATH = EVAL / "criteria-remote-creator.json"
TEMPLATE_PATH = EVAL / "profile-dsh.patch.yml"

# The fill points the workflow substitutes (eval/README.md documents the
# recipe). A marker is deliberately invalid YAML: an unfilled template
# cannot load, so no run ever uses a guessed URL or provider.
MARKERS = {
    "DSH_PROFILE_PROVIDER",
    "DSH_PROFILE_BASE_URL",
    "DSH_PROFILE_MODEL",
    "DSH_PROFILE_CONTEXT_WINDOW",
    "DSH_PROFILE_MAX_TOKENS",
}
# What a literal credential looks like in text. apiKeyEnv names a variable;
# only a value would match these.
LITERAL_KEY = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{8,}|[A-Za-z0-9]{32,}")
LOCAL_HOST = re.compile(r"localhost|127\.0\.0\.1")
# Provider and model identity of the observed runs; the template must not
# carry it, the workflow brings its own.
PINNED_PROVIDER = re.compile(r"omniroute|openrouter|crouton", re.IGNORECASE)


class VersionedCriteriaTest(unittest.TestCase):
    def test_the_versioned_criteria_passes_the_evaluator_contract(self):
        """The pre-registered case is consumable without changing the verdict core.

        `_require_criteria` is the gate the evaluator and the case builder
        actually run: the versioned file must enter it as written, with the
        stable case id landing in the report and no field the core ignores.
        """
        document = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
        accepted = creator_eval._require_criteria(document)
        self.assertEqual(document["id"], "remote-creator-v1")
        self.assertEqual(document["forbidden_schema_reads"],
                         ["modes.schema.json", "skills.schema.json"])
        self.assertIs(document["require_manifest"], True)
        self.assertIs(document["require_prevalidation"], True)
        self.assertEqual(sorted(document),
                         ["forbidden_schema_reads", "id",
                          "require_manifest", "require_prevalidation"])
        self.assertEqual(accepted["id"], document["id"])

    def test_the_evaluator_contract_rejects_a_weakened_criterion(self):
        """Non-vacuity: the gate is real, so a broken case cannot slip through.

        The versioned file is only pinned if `_require_criteria` still
        disagrees with documents that violate it; a gate that accepted
        anything would make the previous test decoration.
        """
        document = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
        missing = {key: value for key, value in document.items()
                   if key != "require_manifest"}
        with self.assertRaises(ValueError):
            creator_eval._require_criteria(missing)
        mistyped = dict(document, require_manifest="true")
        with self.assertRaises(ValueError):
            creator_eval._require_criteria(mistyped)


class ProfileTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_the_profile_template_leaves_identity_to_the_workflow(self):
        """No key, no host, no provider: only fill points the workflow owns.

        The credential appears solely as `apiKeyEnv`, the documented name of
        the environment variable the runner exports from the repository
        secret. The base URL and the provider/model identity are markers the
        workflow substitutes; a literal one would pin somebody's gateway
        into the repository.
        """
        self.assertEqual(re.findall(r"apiKeyEnv:\s*\S+", self.text),
                         ["apiKeyEnv: DSH_PROVIDER_API_KEY"])
        self.assertNotRegex(self.text, LITERAL_KEY)
        self.assertNotRegex(self.text, LOCAL_HOST)
        self.assertNotRegex(self.text, PINNED_PROVIDER)
        # The only URL the template can produce is the marker the workflow
        # substitutes with the public base URL it receives.
        self.assertEqual(re.findall(r"baseURL:\s*\S+", self.text),
                         ["baseURL: @DSH_PROFILE_BASE_URL@"])
        self.assertNotIn("http://", self.text)
        self.assertNotIn("https://", self.text)

    def test_the_profile_template_exposes_exactly_the_documented_fill_points(self):
        """Stray or renamed markers break the documented substitution."""
        self.assertEqual(set(re.findall(r"@([A-Z_]+)@", self.text)), MARKERS)
        for marker in sorted(MARKERS):
            self.assertIn(f"@{marker}@", self.text)

    def test_the_profile_template_keeps_the_loader_contract_that_worked(self):
        """The two loader entries DSH 0.2.1 consumes, over the responses API.

        The entry ids are upstream plugin names, not provider identity; the
        `openai-responses` channel is the one the observed case validated.
        """
        for line in ("- id: llm-pi-ai",
                     'name: "@deepseek-ai/dsh-llm-pi-ai"',
                     "- id: agent-default-model",
                     'name: "@deepseek-ai/dsh-agent-default-model"',
                     "api: openai-responses"):
            self.assertIn(line, self.text)
        # agent-default-model must point at the same fill points, so the
        # substituted profile stays internally consistent.
        self.assertIn("provider: @DSH_PROFILE_PROVIDER@", self.text)
        self.assertIn("model: @DSH_PROFILE_MODEL@", self.text)


if __name__ == "__main__":
    unittest.main()
