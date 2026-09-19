"""Biblioteca base materializada: contrato, contenido y cobertura de escenarios.

Valida library/library.json, las skills base en library/base/ y sus escenarios:
coherencia bidireccional, procedencia registrada, límites de entrada y
saneamiento. Fail-closed: cualquier desajuste rompe la suite.

    python3 -B -m unittest tests.test_library_base -v
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = ROOT / "library"
BASE_DIR = LIBRARY_DIR / "base"

import sys
sys.path.insert(0, str(ROOT / "scripts"))
import generation_contracts as gc


def load_library():
    return json.loads((LIBRARY_DIR / "library.json").read_text(encoding="utf-8"))


def registered_source_ids():
    registry = json.loads(
        (LIBRARY_DIR / "source-registry.json").read_text(encoding="utf-8"))
    return {s["source_id"] for s in registry["sources"]}


class LibraryDocumentTest(unittest.TestCase):
    """El documento de biblioteca materializado cumple su contrato."""

    def setUp(self):
        self.library = load_library()

    def test_library_document_validates(self):
        gc.validate("library", self.library)

    def test_base_skills_present(self):
        self.assertGreaterEqual(len(self.library["base_skills"]), 21)
        names = [b["name"] for b in self.library["base_skills"]]
        self.assertEqual(len(names), len(set(names)),
                         "duplicate base skill names")

    def test_provenance_sources_are_registered(self):
        ids = registered_source_ids()
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                source = entry["provenance"]["source"]
                self.assertIn(source, ids,
                              f"{entry['name']}: source {source!r} not in registry")
                self.assertRegex(entry["provenance"]["commit"],
                                 r"^[0-9a-f]{40}$")

    def test_mvp_skills_not_shadowed(self):
        names = {b["name"] for b in self.library["base_skills"]}
        mvp = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
        self.assertFalse(names & mvp,
                         "base skills must not shadow MVP construction skills")

    def test_legacy_names_absent(self):
        forbidden = {"workflow-auditor", "workflow-complete-auditor",
                     "workflow-continuous-repair"}
        names = {b["name"] for b in self.library["base_skills"]}
        self.assertFalse(names & forbidden)


class BaseSkillContentTest(unittest.TestCase):
    """Cada skill base tiene entrada única, saneada y dentro de presupuesto."""

    def setUp(self):
        self.library = load_library()

    def test_every_entry_has_content_directory(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                d = BASE_DIR / entry["name"]
                self.assertTrue(d.is_dir())
                skill_md = d / "SKILL.md"
                self.assertTrue(skill_md.is_file())
                self.assertFalse(skill_md.is_symlink())

    def test_entrypoint_budget(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                size = (BASE_DIR / entry["name"] / "SKILL.md").stat().st_size
                self.assertLessEqual(size, 32768)

    def test_frontmatter_name_matches_directory(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                text = (BASE_DIR / entry["name"] / "SKILL.md").read_text(
                    encoding="utf-8")
                match = re.match(r"^---\nname: (\S+)\ndescription: \"(.+)\"\n---\n",
                                 text)
                self.assertIsNotNone(match, f"{entry['name']}: frontmatter")
                self.assertEqual(match.group(1), entry["name"])
                self.assertLessEqual(len(match.group(2)), 512)

    def test_content_has_sections_and_scenario_refs(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                text = (BASE_DIR / entry["name"] / "SKILL.md").read_text(
                    encoding="utf-8")
                self.assertIn("## Invariantes", text)
                self.assertIn("## Prohibido y límites", text)
                self.assertIn("## Procedencia", text)
                for scenario_id in entry["scenarios"]:
                    self.assertIn(scenario_id, text)

    def test_content_sanitized(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                text = (BASE_DIR / entry["name"] / "SKILL.md").read_text(
                    encoding="utf-8")
                self.assertNotIn("/home/", text)
                self.assertNotIn("http://", text)

    def test_attribution_present(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                text = (BASE_DIR / entry["name"] / "SKILL.md").read_text(
                    encoding="utf-8")
                self.assertIn("MIT", text)
                self.assertIn("Reimplementación propia", text)


class BaseScenarioCoverageTest(unittest.TestCase):
    """Los escenarios referenciados existen, validan y cubren en ambas direcciones."""

    def setUp(self):
        self.library = load_library()
        self.referenced = {}
        for entry in self.library["base_skills"]:
            for scenario_id in entry["scenarios"]:
                self.referenced.setdefault(scenario_id, set()).add(entry["name"])
        self.on_disk = {}
        for p in sorted(BASE_DIR.glob("*/scenarios/*.json")):
            self.on_disk[p.stem] = p

    def test_referenced_scenarios_exist_and_validate(self):
        for scenario_id, users in self.referenced.items():
            with self.subTest(scenario=scenario_id):
                self.assertIn(scenario_id, self.on_disk)
                doc = gc.validate_json_file("scenario",
                                            str(self.on_disk[scenario_id]))
                self.assertEqual(doc["scenario_id"], scenario_id)
                expected_targets = {doc.get("target_skill")}
                self.assertTrue(expected_targets & users,
                                f"{scenario_id}: target_skill does not match user")

    def test_disk_scenarios_are_referenced(self):
        orphans = set(self.on_disk) - set(self.referenced)
        self.assertEqual(orphans, set(), f"orphan scenarios: {sorted(orphans)}")

    def test_each_skill_has_positive_and_negative(self):
        for entry in self.library["base_skills"]:
            with self.subTest(entry=entry["name"]):
                types = set()
                for scenario_id in entry["scenarios"]:
                    doc = json.loads(self.on_disk[scenario_id].read_text(
                        encoding="utf-8"))
                    types.add(doc["type"])
                self.assertIn("positive", types)
                self.assertGreater(len(types), 1,
                                   "missing a non-positive scenario")

    def test_scenario_expected_verdicts(self):
        for scenario_id, p in self.on_disk.items():
            with self.subTest(scenario=scenario_id):
                doc = json.loads(p.read_text(encoding="utf-8"))
                if doc["type"] == "positive":
                    self.assertEqual(doc["expected"]["verdict"], "PASS")
                else:
                    self.assertIn(doc["expected"]["verdict"],
                                  ("FAIL", "BLOCKED"))


if __name__ == "__main__":
    unittest.main()
