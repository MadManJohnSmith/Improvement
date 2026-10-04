"""E5: a declared verification command is only coverage if it resolves.

Thirty stacks declare how to verify themselves, and only four have been proven
by a real campaign (Syncify/Rust, RehabWeb/Django, LoboApp/Flutter and the
framework itself/Python). The other twenty-six were written from what those
tools document, and a plausible command is not coverage: the LoboApp campaign
proved that the command a plan names is not always the command the mode's shell
can run.

These cases put a real toolchain on PATH for every declared stack and require
the plan to name a command the shell can invoke, then take the toolchain away
and require the plan to name what is missing instead of assuming readiness. The
fixtures are deliberately tiny -- the claim under test is about resolution, not
about the project being realistic.
"""
import json
import os
import shutil
import stat
import subprocess
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
    "deno": ("deno.json", ["deno"], '{"tasks": {"test": "deno test"}}'),
    "bun": ("bunfig.toml", ["bun"], "[install] exact = true"),
    "android-gradle": ("app/build.gradle", ["java", "sdkmanager"],
                       "plugins { id 'com.android.application' }"),
    "swift": ("Package.swift", ["swift"], "// swift-tools-version:5.9 package x"),
    "cmake": ("CMakeLists.txt", ["cmake", "ctest"],
              "cmake_minimum_required(VERSION 3.20) project(x) enable_testing()"),
    "meson": ("meson.build", ["meson"], "project('x')"),
    "sbt": ("build.sbt", ["sbt"], 'ThisBuild / scalaVersion := "3.3.1"'),
    "elixir": ("mix.exs", ["mix"], "defmodule X.MixProject do use Mix.Project end"),
    "erlang": ("rebar.config", ["rebar3"], "{erl_opts, [debug_info]}."),
    "zig": ("build.zig.zon", ["zig"], '.{ .name = "x", .version = "0.1.0" }'),
    "crystal": ("shard.yml", ["crystal"], "name: x version: 0.1.0"),
    "nim": ("x.nimble", ["nimble"], 'version = "0.1.0" author = "x"'),
    "julia": ("Project.toml", ["julia"], 'name = "x" version = "0.1.0"'),
    "r": ("DESCRIPTION", ["R"], "Package: x Version: 0.1.0"),
    "perl": ("Makefile.PL", ["perl", "prove"],
             "use ExtUtils::MakeMaker; WriteMakefile(NAME => 'x');"),
    "clojure": ("deps.edn", ["clojure"], '{:paths ["src"]}'),
    "cabal": ("x.cabal", ["cabal"], "cabal-version: 3.0 name: x version: 0.1.0"),
    "haskell-stack": ("stack.yaml", ["stack"], 'resolver: lts-22.0 packages: ["."]'),
    "dune": ("dune-project", ["dune"], "(lang dune 3.0)"),
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
            marker_path = product / marker
            # A marker may live below the root (android's app/build.gradle):
            # create the directories it needs before writing it.
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(content, encoding="utf-8")
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

    # -- detection priority between overlapping markers ----------------------
    def test_a_bun_project_with_a_package_json_is_bun_not_node(self):
        # A bun project usually carries a package.json too — tooling only reads
        # node's manifest — so the manifest is the weaker signal. STACKS puts
        # bun and deno above node for exactly this: the first stack to match a
        # root keeps it, and the lockfile wins over the manifest.
        product, _, _ = self._project("bun")
        (product / "package.json").write_text('{"name":"x"}\n', encoding="utf-8")
        at_root = [e["stack"] for e in stack_module.detect(product)
                   if e["root"] == ""]
        self.assertEqual(at_root[0], "bun")
        self.assertIn("node", at_root)  # both matched; priority decided

    def test_an_android_project_is_not_mistaken_for_plain_java_gradle(self):
        # An Android app module is a Gradle project too: with build.gradle,
        # settings.gradle and gradlew at the root it matches java-gradle's
        # markers as well. android-gradle sits above it in STACKS so the app/
        # marker claims the root and names the Android entrypoints.
        product, _, _ = self._project("android-gradle")
        for marker in ("build.gradle", "settings.gradle", "gradlew"):
            (product / marker).write_text("// root gradle plumbing\n",
                                          encoding="utf-8")
        at_root = [e["stack"] for e in stack_module.detect(product)
                   if e["root"] == ""]
        self.assertEqual(at_root[0], "android-gradle")
        self.assertIn("java-gradle", at_root)  # both matched; priority decided

    def test_a_gradle_project_with_only_settings_gradle_is_detected(self):
        # A multi-module Gradle project may carry no build.gradle at the root:
        # settings.gradle alone is still a Gradle project, and without those
        # markers in STACKS the detector would leave such a root undeclared.
        base = self.tmp / "gradle-settings-only"
        product = base / "product"
        product.mkdir(parents=True)
        (product / "settings.gradle").write_text("rootProject.name = 'x'\n",
                                                 encoding="utf-8")
        at_root = [e["stack"] for e in stack_module.detect(product)
                   if e["root"] == ""]
        self.assertEqual(at_root, ["java-gradle"])

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


class SelfDeclarationTest(unittest.TestCase):
    """The one declaration that is not a fixture: this repository's own.

    The case above proves the invariant for thirty synthetic products, and the
    product that actually ships a declaration — this repository, through
    `improvement-verification.json` — was outside its reach. That matters more
    than a fixture, because `declared()` checks shape and nothing else: a
    command that lost its last argument is still a list of non-empty strings,
    so the plan would keep answering `verification_ready: true` while naming
    something no shell can run. The other end of that is that a real campaign
    against this framework would record a product failure caused by the
    framework's own declaration.

    So the claim is proven by running it, with a bound: the declared command
    has to survive its own argv. It may still be running when the probe stops
    watching — a full suite is the expected outcome, not a failure — but it may
    not have died on the way in, because that is what a truncated command does,
    in milliseconds.

    The child is stopped the way any probe stops a long command: killed, with
    whatever temporary state it had open left behind in `/tmp` where it belongs.
    Nothing it touches is inside this tree, and the recursion guard keeps it from
    reaching past its own suite.
    """
    #: Set on the child so the suite it starts does not start another one.
    GUARD = "IMPROVEMENT_DECLARED_SELFTEST"
    WATCH_SECONDS = 10.0

    def setUp(self):
        self.plan = stack_module.plan(
            str(ROOT), workspace=str(Path(tempfile.mkdtemp(prefix="self-plan-", dir="/tmp"))),
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")})
        self.addCleanup(shutil.rmtree, Path(self.plan["workspace"]), True)
        entries = [e for e in self.plan["stacks"] if e["stack"] == "python-unittest"]
        self.assertEqual(len(entries), 1, self.plan)
        self.entry = entries[0]

    def _survives(self, command, cwd):
        """Whether a command gets past its own argv, however long it then runs."""
        env = dict(os.environ, **{self.GUARD: "1"})
        try:
            done = subprocess.run(command, cwd=cwd, timeout=self.WATCH_SECONDS,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  env=env)
        except subprocess.TimeoutExpired:
            return True, "sigue corriendo: el argv se aceptó"
        if done.returncode == 0:
            return True, "terminó en verde"
        return False, done.stderr.decode("utf-8", "replace").strip()[-300:]

    @unittest.skipIf(os.environ.get(GUARD), "ya se está probando dentro del comando declarado")
    def test_the_command_this_repo_declares_for_itself_survives_its_own_argv(self):
        self.assertTrue(self.entry["declared"], self.plan)
        self.assertTrue(self.entry["verification_ready"], self.plan)
        survived, why = self._survives(self.entry["verify_command"], ROOT)
        self.assertTrue(survived, f"{self.entry['verify_command']} no arranca: {why}")

    @unittest.skipIf(os.environ.get(GUARD), "el canary no necesita correr dos veces")
    def test_a_truncated_declaration_would_not_pass_that_check(self):
        # The canary: without it, "survives its own argv" is a claim about a
        # command nobody ever ran. It is the declared command with its last
        # argument removed and nothing else changed, which is exactly the
        # regression this file exists to catch.
        broken = [*self.entry["verify_command"][:-1]]
        with tempfile.TemporaryDirectory(prefix="broken-", dir="/tmp") as empty:
            survived, why = self._survives(broken, empty)
        self.assertFalse(survived, f"un comando truncado pasó el chequeo: {why}")


class CampaignEvidenceTest(unittest.TestCase):
    """Which stacks were proven by a real project, and which are only declared.

    These two cases used to read `docs/status.md` and assert that four strings
    appeared somewhere near the heading, with the proven set hardcoded in the
    test body. That passes when the document claims a campaign for Go, which
    never happened, and passes when the registry gains a stack the table never
    mentions. A coverage claim nobody can falsify is not coverage, and the one
    place it mattered most was the table a reader consults before trusting this
    on their own repository.

    So the proven set is declared once, in `stack.CAMPAIGN_EVIDENCE`, next to
    the commands it applies to, and these cases check the table against it in
    both directions: every proven stack says so and names its campaign, and
    every stack without a campaign says so too — which is the direction that
    had no check at all.
    """

    PROOF_WORDS = ("PROBADA", "probada", "campaña real", "campaign")

    def _table_rows(self):
        status = (ROOT / "docs" / "status.md").read_text(encoding="utf-8")
        start = status.index("stack_coverage")
        rows = {}
        for line in status[start:].splitlines():
            if not line.startswith("|"):
                if rows:
                    break
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 3 or cells[0] in ("stack", "---"):
                continue
            rows[cells[0].strip("`")] = cells[2]
        return rows

    def test_the_table_names_every_declared_stack_and_nothing_else(self):
        rows = self._table_rows()
        self.assertEqual(sorted(rows), sorted(stack_module.STACKS))

    def test_only_stacks_with_a_campaign_are_claimed_as_proven(self):
        rows = self._table_rows()
        proven = stack_module.CAMPAIGN_EVIDENCE
        self.assertEqual(sorted(proven), ["dart-flutter", "python-django",
                                          "python-generic", "rust"])
        for stack_name, evidence in sorted(proven.items()):
            with self.subTest(stack=stack_name):
                cell = rows[stack_name]
                self.assertIn("PROBADA", cell, f"{stack_name}: {cell}")
                # The campaign is named, not merely asserted to exist.
                self.assertIn(evidence.split(",")[0].split("(")[0].strip()[:12],
                              cell, f"{stack_name}: {cell}")
        for stack_name, cell in sorted(rows.items()):
            if stack_name in proven:
                continue
            with self.subTest(stack=stack_name):
                # The direction that had no check: a declared stack must not
                # borrow the vocabulary of a proven one.
                self.assertNotIn("PROBADA", cell, f"{stack_name}: {cell}")
                self.assertIn("declarada", cell, f"{stack_name}: {cell}")


if __name__ == "__main__":
    unittest.main()
