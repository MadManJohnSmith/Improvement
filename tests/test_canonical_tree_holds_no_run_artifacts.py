"""The canonical tree carries code, not the result of running it.

`AGENTS.md` is explicit about this and equally explicit about the reason:
projects, session reports, logs, captures, candidates and caches belong outside
this repository, in a sibling of the tests or an explicit temporary directory,
and "no basta con ignorarlos en Git". The `.gitignore` covers the usual names;
ignoring them was never the rule, absence is.

Nothing checked that. The vocabulary below is not invented: it is the set of
filenames the product itself writes into a workspace or a run — taken from
`scripts/`, where they appear as literals — so a run artefact dropped in here
fails by name rather than by judgement. Fixtures are exempt by construction,
because a golden manifest of a real project is deliberately shaped like the
thing it stands for, and `fixtures/` is checked for being sanitised instead.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories that are not the canonical tree's content.
INFRASTRUCTURE = {".git", ".zcode", "__pycache__", "node_modules"}
# Where a run artefact is allowed to be, and why: it is the point of the
# directory, and it is held to its own rule instead.
EXEMPT_ROOTS = {"fixtures"}

# Filenames the product writes outside itself, read off the literals in
# scripts/. Anything carrying one of these is a result, not source.
RUN_ARTIFACTS = {
    "run.json", "work-items.json", "generation-manifest.json", "mode.json",
    "findings.jsonl", "handoffs.jsonl", "verification-results.jsonl",
    "overflows.jsonl", "project.json", "host-verdict.json", "summary.json",
    "acceptance-plan.json", "checkpoint.json", "capabilities.json",
    "published-presets.json", "events.jsonl", "static-retained.json",
    "state-schema.json", "capability-plan.json", "started.json",
    "episodes.jsonl", "episodes-index.json", "instructions-index.json",
    # Both found by the vocabulary check below on its first run, which is what
    # it is for: a hand-copied list of names is already stale the moment the
    # product writes a new one.
    "evidence-ledger.jsonl", "scenarios.jsonl",
}
# Whole directories a run creates, relative to whatever root it ran in.
RUN_DIRECTORIES = {
    "mode-state", "metrics", "decisions", ".dsh-managed", ".dsh", "runs",
    "reports", "candidates", "screenshots", "evidence",
}


def _is_exempt(relative):
    return bool(EXEMPT_ROOTS & set(relative.parts))


class CanonicalTreeTest(unittest.TestCase):
    def entries(self):
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if set(relative.parts) & INFRASTRUCTURE:
                continue
            yield relative

    def test_the_canonical_tree_holds_no_run_artifact(self):
        found = []
        for relative in self.entries():
            if _is_exempt(relative):
                continue
            if relative.name in RUN_ARTIFACTS:
                found.append(str(relative))
            elif set(relative.parts) & RUN_DIRECTORIES:
                found.append(str(relative))
        self.assertEqual(found, [],
                         "artefactos de ejecución dentro del árbol canónico: "
                         f"{found}. AGENTS.md exige que vivan fuera.")

    def test_the_vocabulary_still_matches_what_the_product_writes(self):
        """The list above is only worth anything while it is the real one.

        It is a hand-kept copy of names that live in `scripts/`, so a new state
        file the product starts writing would leave the check guarding yesterday.
        This reads the same literals and requires the copy to cover them.
        """
        scripts = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted((ROOT / "scripts").rglob("*.py")))
        written = set(re.findall(r"['\"]([a-z][a-z0-9-]*\.(?:json|jsonl|md))['\"]", scripts))
        missing = sorted(name for name in written
                         if name not in RUN_ARTIFACTS and _looks_like_state(name))
        self.assertEqual(missing, [],
                         "nombres de estado que el producto escribe y la lista no conoce: "
                         f"{missing}")

    def test_the_exempt_directory_is_held_to_its_own_rule(self):
        """Exemption from this rule is not exemption from the sanitisation one."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "test_fixtures", Path(__file__).resolve().parent / "test_fixtures.py")
        sanitiser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sanitiser)

        fixtures = ROOT / "fixtures"
        self.assertTrue(fixtures.is_dir(), "fixtures/ desapareció: la excepción no apunta a nada")
        for path in sorted(fixtures.rglob("*")):
            if not path.is_file():
                continue
            with self.subTest(fixture=path.name):
                self.assertIsNone(sanitiser.LOCAL_PATH.search(
                    path.read_text(encoding="utf-8")))


def _looks_like_state(name):
    """A state file the product writes, as opposed to a schema or a config."""
    return (name.endswith(".jsonl")
            or name in {"run.json", "work-items.json", "project.json", "mode.json",
                        "started.json", "summary.json", "checkpoint.json"})


if __name__ == "__main__":
    unittest.main()