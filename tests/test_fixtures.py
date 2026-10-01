"""The fixtures this repository publishes are checked, not asserted.

`fixtures/README.md` makes two claims about this directory. The golden manifests
"sirven exclusivamente para validar generadores y validadores de contratos
(C0–C3)", and the files carry no "rutas de usuario, claves, tokens ni sesiones".
Neither claim had a reader: no test, no validator and no script opened anything
under `fixtures/`, so the golden files were decoration and the sanitisation was a
sentence in a README.

Both are cheap to make true and both are worth making true. A golden manifest
that nothing validates is precisely the artefact that drifts in silence when the
contract it was written for moves — the failure mode a golden file exists to
prevent, reproduced by the golden file. And these are the only files in the tree
derived from real projects, so the sanitisation rule is the one that decides
whether they may be published at all.
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import generation_contracts as gc

# The contract each golden file is a golden of.
SCHEMA_OF = {
    "golden-manifest.json": "generation-manifest",
    "project-manifest.json": "project-manifest",
}
# Absolute paths of a machine, not of a project. `/home/alice` in a published
# fixture is somebody's directory; `/opt/app` is not.
LOCAL_PATH = re.compile(
    r"(?<![\w.])/(?:home|Users|root|var/folders)/[\w.-]+"
    r"|[A-Za-z]:\\\\?[\w.\\-]+")
# What a credential looks like in a JSON document. Digests are hex and are not
# on this list; only names that would carry a secret are.
CREDENTIAL_KEY = re.compile(
    r"\"(?:token|secret|password|passwd|api[_-]?key|apikey|bearer|cookie|"
    r"session|authorization|credentials?)\"\s*:", re.IGNORECASE)
BEARER_VALUE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}")


def _fixture_dirs():
    return sorted(path for path in FIXTURES.iterdir() if path.is_dir())


class GoldenFixtureTest(unittest.TestCase):
    def setUp(self):
        self.dirs = _fixture_dirs()
        self.assertTrue(self.dirs, "no hay fixtures: el escaneo está roto")

    def test_every_fixture_directory_carries_both_manifests(self):
        # A fixture with only one of the two is a fixture whose golden side was
        # deleted without anyone noticing, which is the same silence as never
        # having had it.
        for directory in self.dirs:
            with self.subTest(fixture=directory.name):
                for name in SCHEMA_OF:
                    self.assertTrue((directory / name).is_file(),
                                    f"{directory.name} no trae {name}")

    def test_every_golden_manifest_validates_against_the_contract_it_is_golden_of(self):
        """The claim the README makes, executed instead of repeated."""
        seen = set()
        for directory in self.dirs:
            for name, schema in sorted(SCHEMA_OF.items()):
                path = directory / name
                if not path.is_file():
                    continue
                with self.subTest(fixture=directory.name, schema=schema):
                    document = json.loads(path.read_text(encoding="utf-8"))
                    gc.validate(schema, document)
                    seen.add(schema)
        self.assertEqual(seen, set(SCHEMA_OF.values()),
                         "ningún schema quedó probado: el bucle no probó nada")

    def test_the_golden_manifests_are_pinned_rather_than_trivially_valid(self):
        """Non-vacuity: the schema really constrains the fixture it is given.

        A document that satisfies the contract because nothing in it is checked
        would let the generator drift while every golden file stayed green, which
        is the opposite of what a golden file is for.
        """
        path = self.dirs[0] / "golden-manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        gc.validate("generation-manifest", document)
        weakened = copy.deepcopy(document)
        removed = next(key for key in sorted(weakened) if key != "schema_version")
        del weakened[removed]
        with self.assertRaises(gc.ContractError):
            gc.validate("generation-manifest", weakened)


class FixtureSanitationTest(unittest.TestCase):
    """Rule 2 of the fixture README, and rule 4, made mechanical."""

    def files(self):
        return sorted(path for path in FIXTURES.rglob("*") if path.is_file())

    def test_no_fixture_carries_a_local_path(self):
        for path in self.files():
            found = LOCAL_PATH.search(path.read_text(encoding="utf-8"))
            with self.subTest(fixture=path.name):
                self.assertIsNone(
                    found, f"{path.relative_to(ROOT)} contiene una ruta local")

    def test_no_fixture_carries_a_credential(self):
        # The prose that says the fixtures were sanitised mentions the very words
        # this looks for, so the scan runs on the documents that carry data.
        for path in sorted(FIXTURES.rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(fixture=path.name):
                self.assertIsNone(CREDENTIAL_KEY.search(text),
                                  f"{path.relative_to(ROOT)} nombra una credencial")
                self.assertIsNone(BEARER_VALUE.search(text),
                                  f"{path.relative_to(ROOT)} lleva un bearer")

    def test_nothing_in_the_product_can_install_a_fixture(self):
        """Rule 4: these are never installed into someone's project.

        The check is that the product never names the directory, which is the only
        way a copy could start happening without this file noticing.
        """
        for path in sorted((ROOT / "scripts").rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".mjs", ".yml"}:
                continue
            with self.subTest(module=path.name):
                self.assertNotIn("fixtures/", path.read_text(encoding="utf-8"),
                                 "un módulo del producto nombra fixtures/: podría instalarlos")


if __name__ == "__main__":
    unittest.main()