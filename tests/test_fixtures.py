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

The directory later gained a second class of fixture: a complete synthetic
product as the remote evaluation's input. It is not a golden manifest — forcing
one would be a fake manifest — so the gates are divided by declared class
(`FixtureClassTest`): the manifest class keeps every golden gate, the product
class registers its identity as the framework's tree digest and answers to the
same sanitisation, extended to personal data.
"""
import copy
import hashlib
import json
import os
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
# Personal data a published fixture must not carry. The address pattern is
# deliberately narrow: a street name followed by a number is what a real
# postal address looks like, and the false positives it could take are prose
# this directory does not contain.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
POSTAL_ADDRESS = re.compile(
    r"\b(?:calle|avenida|paseo|carrer|avinguda|street|avenue|road|boulevard|"
    r"strasse)\b[^\n]{0,60}?\b\d{1,4}\b", re.IGNORECASE)

# The two fixture classes, declared explicitly (see FixtureClassTest). The
# manifest fixtures keep every golden gate they had; the product class is the
# remote evaluation's input and is gated by ProductFixtureTest below.
MANIFEST_FIXTURES = ("rehabweb", "syncify")
PRODUCT_FIXTURES = ("libreta",)


def _fixture_dirs():
    return sorted(path for path in FIXTURES.iterdir() if path.is_dir())


class FixtureClassTest(unittest.TestCase):
    """fixtures/ holds two fixture classes with different gates.

    The golden manifests exist to validate generators and validators (C0-C3);
    the product fixture is the input of the remote evaluation, a complete
    synthetic product. Which gates apply depends on the class, so the class
    must be declared rather than inferred from the contents: a golden side
    deleted in silence would otherwise reclassify its own fixture as a
    product one.
    """

    def test_every_fixture_directory_is_declared_in_exactly_one_class(self):
        declared = set(MANIFEST_FIXTURES) | set(PRODUCT_FIXTURES)
        actual = {path.name for path in _fixture_dirs()}
        self.assertEqual(
            actual, declared,
            "hay directorios de fixture sin clase declarada o clases sin directorio")


class GoldenFixtureTest(unittest.TestCase):
    """The golden gates, scoped to the manifest fixture class."""

    def setUp(self):
        self.dirs = [FIXTURES / name for name in MANIFEST_FIXTURES]
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

    def test_no_fixture_carries_personal_data(self):
        # The same reasoning as the credential gate: the patterns run over
        # every published file, so a note or a product source cannot carry
        # someone's contact details into the repository.
        for path in self.files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(fixture=path.name):
                self.assertIsNone(
                    EMAIL.search(text),
                    f"{path.relative_to(ROOT)} lleva un correo")
                self.assertIsNone(
                    POSTAL_ADDRESS.search(text),
                    f"{path.relative_to(ROOT)} lleva una dirección postal")

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


class ProductFixtureTest(unittest.TestCase):
    """The product class: a complete synthetic product, not a golden manifest.

    The remote evaluation needs an input the Creator can audit end to end.
    That is not what a golden manifest is for — forcing one would be a fake
    manifest — so the class carries its own product root and its own
    project manifest instead.
    """

    def test_the_product_fixture_is_a_complete_product_root(self):
        self.assertTrue(PRODUCT_FIXTURES,
                        "no hay fixture de producto: la clase está vacía")
        for name in PRODUCT_FIXTURES:
            directory = FIXTURES / name
            with self.subTest(fixture=name):
                self.assertTrue(directory.is_dir(),
                                f"{name} está declarado pero no existe")
                self.assertFalse(
                    (directory / "golden-manifest.json").exists(),
                    "un fixture de producto no es un golden de generadores")
                manifest = directory / "project-manifest.json"
                self.assertTrue(manifest.is_file(),
                                f"{name} no registra su project manifest")
                document = json.loads(manifest.read_text(encoding="utf-8"))
                gc.validate("project-manifest", document)
                product_root = directory / "product"
                self.assertTrue(product_root.is_dir(),
                                f"{name} no lleva raíz de producto")
                sources = sorted(
                    path.relative_to(directory).as_posix()
                    for path in product_root.rglob("*") if path.is_file())
                self.assertIn("product/README.md", sources,
                              "el producto no se explica a su lector")
                self.assertTrue(
                    any(source.endswith(".py") for source in sources),
                    "el producto no lleva código fuente propio")
                self.assertTrue(
                    any("/tests/" in f"/{source}" for source in sources),
                    "el producto no lleva sus pruebas")


def _tree_digest(root):
    """The framework's tree digest, byte for byte.

    `acceptance_reviewer.tree_digest` and `host_validator._candidate_digest`
    agree on this convention: every file sorted by path, each entry carrying
    the relative path, the file's sha256 and its byte size, serialised as
    canonical JSON. No timestamps and no filesystem metadata, which is what
    makes the digest a stable identity for the same content.
    """
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink no permitido en fixture: {path}")
        if path.is_file():
            entries.append({
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            })
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class ProductIdentityTest(unittest.TestCase):
    """The registered identity of a product fixture is its tree digest.

    Commit metadata varies between clones and working copies; the digest of
    the product tree does not. The manifest registers the digest, and this
    gate recomputes it from the bytes so the registration cannot rot.
    """

    def test_the_registered_root_identity_is_the_framework_tree_digest(self):
        for name in PRODUCT_FIXTURES:
            directory = FIXTURES / name
            with self.subTest(fixture=name):
                document = json.loads(
                    (directory / "project-manifest.json").read_text(
                        encoding="utf-8"))
                self.assertEqual(
                    document["root_identity"],
                    _tree_digest(directory / "product"),
                    "la identidad registrada no es el digest del árbol: "
                    "el fixture y su registro han divergido")

    def test_the_identity_is_stable_under_filesystem_metadata(self):
        """Recalculating twice agrees, and touching mtimes moves nothing.

        The identity travels between working copies whose commit metadata and
        timestamps differ; if the digest followed the filesystem rather than
        the bytes, the registration would rot on every clone. The mutated
        copy keeps the test honest: a digest that ignored content altogether
        would fail the last assertion, not pass it.
        """
        import shutil
        import tempfile
        for name in PRODUCT_FIXTURES:
            product_root = FIXTURES / name / "product"
            with self.subTest(fixture=name):
                self.assertEqual(_tree_digest(product_root),
                                 _tree_digest(product_root))
                copy = Path(tempfile.mkdtemp()) / "product"
                self.addCleanup(shutil.rmtree, copy.parent,
                                ignore_errors=True)
                shutil.copytree(product_root, copy)
                self.assertEqual(_tree_digest(copy), _tree_digest(product_root),
                                 "una copia idéntica cambia de identidad")
                later = copy.stat().st_mtime + 987654
                for path in copy.rglob("*"):
                    if path.is_file():
                        os.utime(path, (later, later))
                self.assertEqual(_tree_digest(copy), _tree_digest(product_root),
                                 "los mtimes mueven la identidad")
                mutated = copy / "src" / "libreta" / "__init__.py"
                mutated.write_text(
                    mutated.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8")
                self.assertNotEqual(_tree_digest(copy),
                                    _tree_digest(product_root),
                                    "cambiar el contenido no mueve la identidad")


if __name__ == "__main__":
    unittest.main()
