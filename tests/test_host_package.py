"""The deterministic Host package: one install command, no Creator turn.

    python3 -B -m unittest tests.test_host_package -v

Born from the Syncify campaign (2026-10-25): the Creator gate has nine
measured runs without ``ACTIVE``, so the operator needs the modes without
waiting for that gate. ``install --host-package`` produces the generation
package with deterministic Host tools — the pattern the 2026-10-10 full pass
declared — and never spends a model token. What these tests pin down:

* the run reaches ``GENERATED`` with a complete package and **no DSH session**;
* the package is portable (no absolute paths), anchored to the run's facts
  and to the roles the scaffold actually wrote;
* the origin is declared (``creator_limit``), so no run of this path can be
  read as a Creator success;
* the CLI flag reaches the function.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap
import creator_client as cc

# install() y la cadena emiten progreso humano por stderr por diseño
# (IMPROVEMENT_QUIET=1 lo apaga); sin esto, la salida de la suite se
# llena de líneas de progreso que se leen como fallos.
os.environ.setdefault("IMPROVEMENT_QUIET", "1")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "Syncify"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.workspace = self.root / "Syncify-workspace"

    def install_host_package(self):
        return bootstrap.install(
            self.project, self.workspace, dispatch_creator=True,
            finalize_host=False, host_package=True)


class HostPackageGeneration(Base):

    def test_reaches_generated_without_any_dsh_session(self):
        result = self.install_host_package()
        self.assertEqual(result["host_package"]["result"], "GENERATED")
        run_dir = Path(result["run_dir"])
        self.assertEqual(
            json.loads((run_dir / "run.json").read_text())["status"],
            "GENERATED")
        self.assertTrue((run_dir / "finish.json").is_file())
        # No Creator turn ran: no session state, and the result never claims
        # a creator key.
        self.assertFalse((run_dir / cc.CREATOR_SESSION_FILE).exists())
        self.assertNotIn("creator", result)

    def test_manifest_and_capabilities_derive_from_run_facts(self):
        result = self.install_host_package()
        generated = Path(result["run_dir"]) / "generated"
        manifest = json.loads(
            (generated / "generation-manifest.json").read_text())
        self.assertEqual(manifest["status"], "GENERATED")
        self.assertGreaterEqual(len(manifest["artifacts"]), 12)
        capabilities = json.loads(
            (generated / "capabilities.json").read_text())
        self.assertEqual(
            set(manifest["required_capabilities"]),
            set(capabilities["required_capabilities"]))
        # The roots are the portable names the modes declare, never paths.
        self.assertEqual(capabilities["roots"]["product_read"], ["Syncify"])
        self.assertNotIn("/home/", (generated / "capabilities.json").read_text())
        self.assertNotIn("/home/", (generated / "capabilities.json").read_text())
        # The project manifest is the discovery's own, not a transcription.
        project_manifest = json.loads(
            (generated / "project-manifest.json").read_text())
        self.assertEqual(project_manifest["name"], "syncify")

    def test_acceptance_plan_anchors_real_roles_and_declares_origin(self):
        result = self.install_host_package()
        generated = Path(result["run_dir"]) / "generated"
        plan = json.loads((generated / "acceptance-plan.json").read_text())
        self.assertEqual(plan["generation_id"], result["generation_id"])
        targets = {s["target"] for s in plan["public_scenarios"]}
        mode_names = {p.name for p in (generated / "modes").iterdir()}
        self.assertTrue(targets <= mode_names, (targets, mode_names))
        types = {s["type"] for s in plan["public_scenarios"]}
        self.assertIn("write-violation", types)
        # The origin is declared: this path can never read as a Creator win.
        self.assertIn("deterministas", plan["creator_limit"])
        self.assertIn("sin exito de Creator", plan["creator_limit"])

    def test_honest_message_names_the_origin(self):
        result = self.install_host_package()
        self.assertIn("Paquete-Host: GENERATED", result["message"])
        self.assertIn("sin turno de Creator", result["message"])

    def test_resume_over_generated_run_does_not_redispatch(self):
        first = self.install_host_package()
        again = bootstrap.install(
            self.project, self.workspace, dispatch_creator=True,
            finalize_host=False, host_package=True)
        self.assertEqual(again["result"], "EXISTING")
        self.assertEqual(again["generation_id"], first["generation_id"])
        self.assertNotIn("host_package", again)
        self.assertNotIn("creator", again)


class HostPackageCLI(Base):

    def test_cli_flag_produces_generated_package(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "bootstrap.py"),
             "install", "--project", str(self.project),
             "--host-package", "--no-finalize"],
            capture_output=True, text=True, env=env, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("Paquete-Host: GENERATED", payload["message"])
        run_dir = Path(payload["run_dir"])
        self.assertEqual(
            json.loads((run_dir / "run.json").read_text())["status"],
            "GENERATED")


if __name__ == "__main__":
    unittest.main()
