"""Transactional publication of exactly two DSH user presets."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import transaction as tx


MODE_COMPOSITION = """- id: persona
  name: '@deepseek-ai/dsh-persona'
- id: tool-bash
  name: '@deepseek-ai/dsh-tool-bash'
- id: tool-fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: tool-fs-search
  name: '@deepseek-ai/dsh-tool-fs-search'
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
"""


class Client:
    def __init__(self, ids=("project-auditor", "project-continuous-repair"), broken=None,
                 application="applied", active_bundle=None):
        self.ids = ids
        self.broken = broken
        self.application = application
        self.active_bundle = Path(active_bundle) if active_bundle else None
        self.authenticated = True
        self.installed = []
        self.removed = []
    def install_bundle(self, path):
        path = Path(path)
        self.installed.append(path)
        if self.application == "applied":
            self.active_bundle = path
        return {"value": {"application": self.application}}
    def remove_bundle(self, name):
        self.removed.append(name)
        self.active_bundle = None
        return {"value": {"application": "applied"}}
    def list_agent_presets(self):
        return {"value": {"presets": [
            {"id": value, "broken": value == self.broken}
            for value in self.ids]}}
    def read_agent_preset(self, preset_id):
        if self.active_bundle is None:
            raise ValueError("preset not active")
        return {"value": {
            "agentPreset": preset_id,
            "content": MODE_COMPOSITION + "    customSkillDirs:\n      - " +
                       str((self.active_bundle / "skills").resolve()) + "\n",
        }}


def verdict(generation="gen-1", value="READY_FOR_INSTALL"):
    return {"generation_id": generation, "verdict": value}


class TransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "project-workspace"
        self.workspace.mkdir()
        (self.workspace / "project.json").write_text(json.dumps({
            "schema": 1, "name": "project", "project": str(self.root / "project")}) + "\n")
        (self.root / "project").mkdir()
        self.home = self.root / "dsh-home"
        self.generated = self._package(self.root / "generated")

    def _package(self, root, marker="one"):
        root.mkdir()
        (root / "generation-manifest.json").write_text("{}\n")
        skill = root / "skills" / "project-check"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: project-check\ndescription: Project check\n---\n# Check\n")
        resources = skill / "resources"
        resources.mkdir()
        (resources / "guide.txt").write_text("guide\n")
        for role in ("auditor", "continuous-repair"):
            preset_id = f"project-{role}"
            mode = root / "modes" / preset_id
            mode.mkdir(parents=True)
            (mode / "mode.json").write_text(json.dumps({
                "preset_id": preset_id, "role": role}) + "\n")
            (mode / "preset.yml").write_text(f"name: {preset_id}\n")
            (mode / "agent.cordis.yml").write_text(
                f"# {marker}\n" + MODE_COMPOSITION)
            (mode / "SKILL.md").write_text(
                f"---\nname: {preset_id}\ndescription: {role} mode\n---\n# {preset_id}\n")
        return root

    def install(self, generated=None, generation="gen-1", client=None, **kwargs):
        self.client = client or getattr(self, "client", None) or Client()
        return tx.install(self.workspace, generated or self.generated, generation,
                          host_verdict=kwargs.pop("host_verdict", verdict(generation)),
                          dsh_home=self.home, client=self.client, **kwargs)

    def uninstall(self):
        return tx.uninstall(self.workspace, dsh_home=self.home,
                            client=self.client)

    def test_requires_host_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "Veredicto Host"):
            tx.install(self.workspace, self.generated, "gen-1",
                       dsh_home=self.home, client=Client())

    def test_rejects_non_installable_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "no aprobó"):
            self.install(host_verdict=verdict(value="RETAINED"))

    def test_publishes_two_presets_and_shared_state_then_activates(self):
        result = self.install()
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), {
            "project-auditor", "project-continuous-repair"})
        receipt = json.loads((self.workspace / ".dsh-managed" /
                              "published-presets.json").read_text())
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["bundle_name"], "@improvement/project-presets")
        bundle = Path(receipt["bundle_path"])
        self.assertTrue((bundle / "package.json").is_file())
        patch = (bundle / "cordis.patch.yml").read_text()
        self.assertIn("preset-project-auditor", patch)
        self.assertIn("preset-project-continuous-repair", patch)
        for plugin in (
                "dsh-persona", "dsh-tool-bash", "dsh-tool-fs",
                "dsh-tool-fs-search", "dsh-skill-filesystem", "dsh-tool-skill"):
            self.assertEqual(
                patch.count(f"name: '@deepseek-ai/{plugin}'"), 2)
        self.assertEqual(patch.count("includeDefaultRoots: false"), 2)
        skill_root = bundle / "skills"
        self.assertEqual(patch.count(str(skill_root.resolve())), 2)
        self.assertEqual(receipt["preset_ids"], [
            "project-auditor", "project-continuous-repair"])
        for name in ("project-auditor", "project-continuous-repair", "project-check"):
            self.assertTrue((skill_root / name / "SKILL.md").is_file())
        self.assertEqual(
            (skill_root / "project-check" / "resources" / "guide.txt").read_text(),
            "guide\n")
        self.assertEqual(self.client.installed, [bundle])
        descriptor = json.loads((self.workspace / "mode-state" / "project.json").read_text())
        self.assertEqual(descriptor["product_root"], "project")
        self.assertEqual(descriptor["state_root"], "project-workspace/mode-state")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(), "gen-1")

    def test_direct_transaction_rejects_incomplete_composition(self):
        composition = self.generated / "modes/project-auditor/agent.cordis.yml"
        composition.write_text(
            "- id: persona\n  name: '@deepseek-ai/dsh-persona'\n")
        with self.assertRaisesRegex(tx.TransactionError, "exactly once"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_transaction_rejects_prohibited_composition(self):
        composition = self.generated / "modes/project-auditor/agent.cordis.yml"
        composition.write_text(MODE_COMPOSITION +
            "- id: workflow\n  name: '@deepseek-ai/dsh-tool-workflow'\n")
        with self.assertRaisesRegex(tx.TransactionError, "prohibited plugin rows"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_bundle_rejects_skill_collision_with_mode(self):
        collision = self.generated / "skills" / "project-auditor"
        collision.mkdir()
        (collision / "SKILL.md").write_text(
            "---\nname: project-auditor\ndescription: Collision\n---\n")
        with self.assertRaisesRegex(tx.TransactionError, "Colisión de skill"):
            self.install()

    def test_bundle_rejects_symlink_in_skill_resources(self):
        resource = self.generated / "skills/project-check/resources/guide.txt"
        resource.unlink()
        resource.symlink_to(self.generated / "generation-manifest.json")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.install()

    def test_roster_failure_rolls_back_both_presets_and_no_active_pointer(self):
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(client=Client(ids=("project-auditor",)))
        self.assertIn("@improvement/project-presets", self.client.removed)
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())

    def test_broken_roster_entry_rolls_back(self):
        with self.assertRaisesRegex(tx.TransactionError, "sano"):
            self.install(client=Client(broken="project-continuous-repair"))

    def test_uninstall_removes_unmodified_managed_presets_preserves_state(self):
        self.install()
        result = self.uninstall()
        self.assertEqual(set(result["removed_presets"]), {
            "project-auditor", "project-continuous-repair"})
        self.assertTrue((self.workspace / "mode-state" / "project.json").is_file())
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())

    def test_uninstall_refuses_modified_managed_bundle(self):
        self.install()
        receipt = json.loads((self.workspace / ".dsh-managed" /
                              "published-presets.json").read_text())
        bundle = Path(receipt["bundle_path"])
        (bundle / "cordis.patch.yml").write_text("modified\n")
        with self.assertRaisesRegex(tx.TransactionError, "modificado"):
            self.uninstall()
        self.assertTrue((bundle / "cordis.patch.yml").is_file())
        self.assertEqual(self.client.removed, [])

    def test_rollback_after_publication_restores_previous_bundle_and_receipt(self):
        self.install()
        receipt_path = self.workspace / ".dsh-managed" / "published-presets.json"
        old_receipt = json.loads(receipt_path.read_text())
        generated = self._package(self.root / "generated-two", marker="two")
        original_inventory = tx._inventory

        def fail_post_publication(path):
            result = original_inventory(path)
            if Path(path) == self.workspace / ".dsh-managed" / "generations" / "gen-2":
                return {**result, "tampered": {"sha256": "bad", "size_bytes": 0}}
            return result

        with unittest.mock.patch("transaction._inventory", side_effect=fail_post_publication):
            with self.assertRaisesRegex(tx.TransactionError, "post-swap"):
                self.install(generated=generated, generation="gen-2")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")
        restored = json.loads(receipt_path.read_text())
        self.assertEqual(restored, old_receipt)
        self.assertIn(old_receipt["bundle_name"], self.client.removed)
        self.assertIn(Path(old_receipt["bundle_path"]), self.client.installed)

    def test_update_rollback_then_same_generation_retry_reuses_manifest(self):
        self.install()
        generated = self._package(self.root / "generated-two", marker="two")
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(generated=generated, generation="gen-2",
                         client=Client(ids=("project-auditor",)))
        manifest = self.workspace / ".dsh-managed" / "backups" / "gen-2.json"
        manifest_before = manifest.read_bytes()
        result = self.install(generated=generated, generation="gen-2",
                              client=Client())
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_update_restart_required_with_stale_roster_does_not_activate(self):
        self.install()
        old_receipt = json.loads((self.workspace / ".dsh-managed" /
                                  "published-presets.json").read_text())
        generated = self._package(self.root / "generated-two", marker="two")
        client = Client(application="restart-required",
                        active_bundle=old_receipt["bundle_path"])

        result = self.install(generated=generated, generation="gen-2", client=client)

        self.assertEqual(result["result"], "RESTART_REQUIRED")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")
        self.assertEqual(json.loads((self.workspace / ".dsh-managed" /
                                    "published-presets.json").read_text()), old_receipt)
        self.assertEqual(client.removed, [])

    def test_update_resumes_after_restart_without_reinstalling(self):
        self.install()
        generated = self._package(self.root / "generated-two", marker="two")
        waiting = Client(application="restart-required")
        first = self.install(generated=generated, generation="gen-2", client=waiting)
        candidate_bundle = waiting.installed[0]
        relaunched = Client(application="restart-required",
                            active_bundle=candidate_bundle)

        result = self.install(generated=generated, generation="gen-2",
                              client=relaunched)

        self.assertEqual(first["result"], "RESTART_REQUIRED")
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(relaunched.installed, [])
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-2")

    def test_retry_after_roster_failure_republishes_incomplete_generation(self):
        with self.assertRaisesRegex(tx.TransactionError, "agentPresets/list"):
            self.install(client=Client(ids=("project-auditor",)))
        result = self.install(client=Client())
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")

    def test_transaction_requires_explicit_resolved_home(self):
        with self.assertRaisesRegex(tx.TransactionError, "home resuelto"):
            tx.Transaction(self.workspace, dsh_home=None)

    def test_direct_install_cli_requires_dsh_home(self):
        result = subprocess.run([
            sys.executable, "-B", str(ROOT / "scripts" / "transaction.py"),
            "install", "--workspace", str(self.workspace), "--generated",
            str(self.generated), "--generation-id", "gen-1",
            "--host-verdict", str(self.root / "verdict.json")],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--dsh-home", result.stderr)

    def _direct_install_args(self):
        verdict_path = self.root / "verdict.json"
        verdict_path.write_text(json.dumps(verdict()) + "\n")
        return [
            "install", "--workspace", str(self.workspace), "--generated",
            str(self.generated), "--generation-id", "gen-1",
            "--host-verdict", str(verdict_path), "--dsh-home", str(self.home),
        ]

    def test_direct_install_cli_succeeds_with_authenticated_matching_client(self):
        client = Client()
        client.resolved_dsh_home = self.home
        stdout = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(client, "controlled runtime")) as acquire, \
             unittest.mock.patch("acceptance.validate_host_verdict",
                                 return_value=verdict()), \
             contextlib.redirect_stdout(stdout):
            tx.main(self._direct_install_args())
        acquire.assert_called_once_with(launch=False)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), {
            "project-auditor", "project-continuous-repair"})
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")

    def test_direct_install_cli_fails_when_no_authenticated_runtime_available(self):
        stderr = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(None, "sin sesión DSH autenticada")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as failure:
                tx.main(self._direct_install_args())
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("DSH no disponible", stderr.getvalue())
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_install_cli_fails_when_runtime_home_mismatches_argument(self):
        client = Client()
        client.resolved_dsh_home = self.root / "other-dsh-home"
        stderr = io.StringIO()
        with unittest.mock.patch(
                "creator_client.acquire_dsh_client",
                return_value=(client, "controlled runtime")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as failure:
                tx.main(self._direct_install_args())
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("no coincide con --dsh-home", stderr.getvalue())
        self.assertFalse((self.workspace / ".dsh-managed").exists())


if __name__ == "__main__":
    unittest.main()
