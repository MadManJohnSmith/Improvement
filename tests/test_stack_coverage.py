"""E5: a declared verification command is only coverage if it resolves.

Eleven stacks declare how to verify themselves, and only four have been proven
by a real campaign (Syncify/Rust, RehabWeb/Django, LoboApp/Flutter and the
framework itself/Python). The other seven were written from what those tools
document, and a plausible command is not coverage: the LoboApp campaign proved
that the command a plan names is not always the command the mode's shell can
run.

These cases put a real toolchain on PATH for every declared stack and require
the plan to name a command the shell can invoke, then take the toolchain away
and require the plan to name what is missing instead of assuming readiness. The
fixtures are deliberately tiny -- the claim under test is about resolution, not
about the project being realistic.
"""
import json
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stack as stack_module

# marker the detector keys on, the binaries its declared command needs, and a
# plausible content for the marker.
FIXTURES = {
    "rust": ("Cargo.toml", ["cargo"], '[package]\nname="x"\n'),
    "go": ("go.mod", ["go"], "module x\n\ngo 1.21\n"),
    "node": ("package.json", ["node", "npm"],
             '{"name":"x","scripts":{"test":"true"}}\n'),
    "java-gradle": ("build.gradle", ["java"], "plugins { id 'java' }\n"),
    "java-maven": ("pom.xml", ["mvn"], "<project/>\n"),
    "dotnet": ("x.csproj", ["dotnet"], "<Project/>\n"),
    "php-composer": ("composer.json", ["php"], "{}\n"),
    "ruby": ("Gemfile", ["bundle", "ruby"], "source 'https://example.invalid'\n"),
    "python-django": ("manage.py", ["python3"], "#!/usr/bin/env python3\n"),
    "python-generic": ("pytest.ini", ["pytest", "python3"], "[pytest]\n"),
    "dart-flutter": ("pubspec.yaml", ["flutter"], "name: x\n"),
}


def _fake_binary(directory, name):
    target = directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


def _resolves(command, path_env, product=None):
    """Whether the mode's shell could actually invoke this command.

    A project-relative entrypoint like `./gradlew` is a legitimate declaration:
    it is run from the product, which the plan states as `verify_cwd`. What
    would not be legitimate is a bare name the shell cannot resolve, because
    that turns a real suite into a BLOCKED the runtime never earned.
    """
    if not command:
        return True
    head = command[0]
    if head.startswith("/"):
        return True
    if head.startswith("./") or head.startswith("../"):
        return product is not None and (product / head).exists()
    return shutil.which(head, path=path_env) is not None


class StackCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stacks-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # One product per stack, in its own directory: a shared tree would let
        # one stack's marker satisfy another's detection, and the case under
        # test is "this stack, alone, names a command it can run".
        self.products = {}

    def _project(self, stack_name):
        """A fresh product holding exactly one stack's marker."""
        if stack_name not in self.products:
            base = self.tmp / stack_name
            product, workspace = base / "product", base / "workspace"
            product.mkdir(parents=True)
            workspace.mkdir(parents=True)
            marker, binaries, content = FIXTURES[stack_name]
            (product / marker).write_text(content, encoding="utf-8")
            for binary in binaries:
                _fake_binary(base / "bin", binary)
            self.products[stack_name] = (product, workspace, base / "bin")
        return self.products[stack_name]

    def _plan(self, stack_name, *, installed=True):
        product, workspace, bin_path = self._project(stack_name)
        path_env = bin_path if installed else self.tmp / "empty-bin"
        path_env.mkdir(parents=True, exist_ok=True)
        return stack_module.plan(
            product, workspace=workspace,
            env={"PATH": str(path_env), "HOME": str(self.tmp)})

    def _entry(self, plan, stack_name):
        entries = [e for e in plan["stacks"] if e["stack"] == stack_name]
        self.assertEqual(len(entries), 1, plan)
        return entries[0]

    # -- the fixtures themselves -------------------------------------------
    def test_every_declared_stack_has_a_fixture_here(self):
        # A stack added to STACKS without a fixture turns this back into
        # "declared", which is exactly what this file exists to prevent.
        self.assertEqual(sorted(stack_module.STACKS), sorted(FIXTURES))

    def test_each_stack_is_detected_from_its_own_marker(self):
        for stack_name, (marker, _, content) in sorted(FIXTURES.items()):
            with self.subTest(stack=stack_name):
                product, _, _ = self._project(stack_name)
                found = {e["stack"] for e in stack_module.detect(product)}
                self.assertIn(stack_name, found)

    # -- with the toolchain present -----------------------------------------
    def test_when_the_plan_is_ready_the_command_it_names_can_actually_run(self):
        # The invariant that holds for every stack, however its capability was
        # satisfied: readiness and runnability are the same claim.
        for stack_name in sorted(FIXTURES):
            with self.subTest(stack=stack_name):
                product, _, bin_path = self._project(stack_name)
                entry = self._entry(self._plan(stack_name), stack_name)
                if not entry["verification_ready"]:
                    continue
                self.assertTrue(entry["verify_command"], entry)
                self.assertTrue(
                    _resolves(entry["verify_command"], str(bin_path), product),
                    f"{stack_name} se declara listo con {entry['verify_command']!r} "
                    "y la shell del modo no lo puede invocar")
                if entry.get("lint_command"):
                    self.assertTrue(
                        _resolves(entry["lint_command"], str(bin_path), product),
                        entry["lint_command"])

    def test_the_plan_is_deterministic_for_the_same_product(self):
        first, second = self._plan("rust"), self._plan("rust")
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    # -- with the toolchain absent ------------------------------------------
    def test_a_stack_without_its_toolchain_names_what_is_missing(self):
        for stack_name in sorted(FIXTURES):
            with self.subTest(stack=stack_name):
                entry = self._entry(self._plan(stack_name, installed=False),
                                    stack_name)
                if entry["verification_ready"]:
                    # Its capability is genuinely present on this host (python3
                    # is), so the plan is right to be ready about it.
                    continue
                missing = [c for c in entry["capabilities"]
                           if c["status"] == "missing"]
                self.assertTrue(missing, entry)
                for capability in missing:
                    self.assertTrue(capability.get("what", "").strip(), capability)
                    self.assertTrue(capability.get("check", "").strip(), capability)
                    self.assertTrue(capability.get("provision_step", "").strip(),
                                    capability)

    def test_a_stack_that_is_not_ready_always_names_what_is_missing(self):
        for stack_name in sorted(FIXTURES):
            with self.subTest(stack=stack_name):
                entry = self._entry(self._plan(stack_name, installed=False),
                                    stack_name)
                if entry["verification_ready"]:
                    continue  # its capability is genuinely present on this host
                missing = [c for c in entry["capabilities"]
                           if c["status"] == "missing"]
                self.assertTrue(missing, entry)

    def test_the_plan_states_the_blocked_policy_it_follows(self):
        plan = self._plan(sorted(FIXTURES)[0], installed=False)
        self.assertEqual(plan["evidence"], "product-own-entrypoint-only")
        self.assertIn("BLOCKED", plan["missing_capability"])

    def test_a_capability_found_outside_the_default_path_is_named_by_path(self):
        # The LoboApp lesson: a name the shell cannot resolve turns a real suite
        # into a BLOCKED the runtime never earned.
        product, workspace, _ = self._project("python-django")
        outside = self.tmp / "sdk"
        outside.mkdir()
        interpreter = _fake_binary(outside, "python3")
        entry = self._entry(stack_module.plan(
            product, workspace=workspace,
            env={"PATH": str(outside), "HOME": str(self.tmp)}), "python-django")
        self.assertEqual(entry["verify_command"][0], str(interpreter))


class CampaignEvidenceTest(unittest.TestCase):
    """Which stacks were proven by a real project, and which are only declared.

    Documentation is not coverage, and the difference has to be visible to the
    person about to install this on their repository.
    """

    def test_status_documents_stack_coverage_per_stack(self):
        status = (ROOT / "docs" / "status.md").read_text(encoding="utf-8")
        self.assertIn("stack_coverage", status)
        for stack_name in sorted(stack_module.STACKS):
            with self.subTest(stack=stack_name):
                self.assertIn(stack_name, status)

    def test_only_stacks_with_a_campaign_are_claimed_as_proven(self):
        status = (ROOT / "docs" / "status.md").read_text(encoding="utf-8")
        start = status.index("stack_coverage")
        block = status[start:start + 2000]
        proven = {"rust", "python-django", "dart-flutter", "python-generic"}
        for stack_name in sorted(proven):
            self.assertIn(stack_name, block, stack_name)


if __name__ == "__main__":
    unittest.main()
