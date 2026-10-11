"""Transactional publication of legacy two and new three DSH presets."""
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
import stack
import acceptance
import acceptance_reviewer
from mode_lifecycle import expected_lifecycle, persona_prefix


def mode_composition(preset_id):
    return f"""- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    prefix: {json.dumps(persona_prefix(preset_id))}
- id: tool-bash
  name: '@deepseek-ai/dsh-tool-bash'
- id: tool-fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: tool-fs-search
  name: '@deepseek-ai/dsh-tool-fs-search'
  config:
    sampleOverCapGlobResults: false
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: anti-escalation
  name: './anti-escalation.mjs'
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
        content = mode_composition(preset_id).replace(
            "'./anti-escalation.mjs'",
            str((self.active_bundle / "anti-escalation.mjs").resolve()))
        return {"value": {
            "agentPreset": preset_id,
            "content": content + "    customSkillDirs:\n      - " +
                       str((self.active_bundle / "skills").resolve()) + "\n",
        }}


def verdict(generation="gen-1", value="READY_FOR_INSTALL"):
    return {"generation_id": generation, "verdict": value}


class TransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "Syncify-workspace"
        self.workspace.mkdir()
        (self.workspace / "project.json").write_text(json.dumps({
            "schema": 1, "name": "project", "project": str(self.root / "Syncify")}) + "\n")
        (self.root / "Syncify").mkdir()
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
            layout = {
                "session_root": self.root.name,
                "product_root": "Syncify",
                "workspace_root": "Syncify-workspace",
                "state_root": "Syncify-workspace/mode-state",
            }
            lifecycle = expected_lifecycle(role, layout)
            (mode / "mode.json").write_text(json.dumps({
                "preset_id": preset_id, "role": role,
                "reads": [layout["product_root"]],
                "writes": [layout["state_root"]],
                "mode_lifecycle": lifecycle}) + "\n")
            (mode / "preset.yml").write_text(f"name: {preset_id}\n")
            (mode / "agent.cordis.yml").write_text(
                f"# {marker}\n" + mode_composition(preset_id))
            (mode / "SKILL.md").write_text(
                f"---\nname: {preset_id}\ndescription: {role} mode\n---\n"
                f"# {preset_id}\n```json mode-layout\n"
                f"{json.dumps(layout, separators=(',', ':'))}\n```\n"
                f"```json mode-lifecycle\n"
                f"{json.dumps(lifecycle, separators=(',', ':'))}\n```\n")
        return root

    def install(self, generated=None, generation="gen-1", client=None, **kwargs):
        self.client = client or getattr(self, "client", None) or Client()
        supplied = kwargs.pop("host_verdict", None)
        if supplied is None:
            supplied = verdict(generation)
        if isinstance(supplied, dict):
            verdict_path = self.root / "host-verdict.json"
            verdict_path.write_text(json.dumps(supplied) + "\n")
            supplied = verdict_path
        with unittest.mock.patch("acceptance.validate_host_verdict", return_value=verdict(generation)):
            return tx.install(self.workspace, generated or self.generated, generation,
                              host_verdict=supplied,
                              dsh_home=self.home, client=self.client, **kwargs)

    def _host_run(self, generated, generation):
        """A real acceptance run: the artifacts the Host binds a verdict to."""
        run = self.root / f"acceptance-run-{generation}"
        (run / "validation").mkdir(parents=True)
        (run / "acceptance").mkdir()
        plan = {"schema_version": 1, "generation_id": generation,
                "requirements": [], "gates": [], "creator_limit": "Host only."}
        (generated / "acceptance-plan.json").write_text(json.dumps(plan) + "\n")
        (run / "validation" / "summary.json").write_text(
            json.dumps({"generation_id": generation, "layers": []}) + "\n")
        return run

    def _host_verdict(self, run, generated, generation):
        """Emit the verdict acceptance.validate_host_verdict would emit.

        Built from the product's own digest helpers so the fixture cannot drift
        away from the binding it is supposed to exercise.
        """
        doc = {
            "schema_version": acceptance.SCHEMA_VERSION,
            "generation_id": generation,
            "verdict": "READY_FOR_INSTALL",
            "static_passed": True,
            "acceptance_plan_valid": True,
            "dynamic_evaluation": "NOT_RUN",
            "candidate_digest": acceptance_reviewer.tree_digest(generated),
            "manifest_digest": acceptance._digest_file(
                generated / "generation-manifest.json"),
            "validation_summary_digest": acceptance._digest_file(
                run / "validation" / "summary.json"),
            "acceptance_plan_digest": acceptance._digest_file(
                generated / "acceptance-plan.json"),
            "host_policy_digest": acceptance.current_host_policy_digest(),
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        path = run / "acceptance" / "host-verdict.json"
        path.write_text(json.dumps(doc) + "\n")
        return path

    def install_bound(self, generated=None, generation="gen-1", client=None,
                      verdict_path=None, verdict_generation=None, **kwargs):
        """Install with the real acceptance binding: no mock of any digest check."""
        self.client = client or getattr(self, "client", None) or Client()
        generated = generated or self.generated
        if verdict_path is None:
            run = self._host_run(generated, generation)
            verdict_path = self._host_verdict(
                run, generated, verdict_generation or generation)
        return tx.install(self.workspace, generated, generation,
                          host_verdict=verdict_path, dsh_home=self.home,
                          client=self.client, **kwargs)

    def uninstall(self):
        return tx.uninstall(self.workspace, dsh_home=self.home,
                            client=self.client)

    def test_requires_host_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "Veredicto Host"):
            tx.install(self.workspace, self.generated, "gen-1",
                       dsh_home=self.home, client=Client())

    def test_rejects_unbound_in_memory_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "ruta"):
            tx.install(self.workspace, self.generated, "gen-1",
                       host_verdict=verdict(), dsh_home=self.home, client=Client())

    def test_rejects_non_installable_verdict(self):
        with self.assertRaisesRegex(tx.TransactionError, "no aprobó"):
            self.install(host_verdict=verdict(value="RETAINED"))

    def test_installs_with_a_real_host_verdict_and_no_mocked_binding(self):
        """IMP-AUD-007: publication is bound to this candidate by the real check.

        The rest of this class mocks acceptance.validate_host_verdict, so with the
        mock in place a verdict for another candidate, or a candidate mutated
        after acceptance, would still publish. This installation runs the real
        binding against a verdict acceptance itself could have emitted.
        """
        result = self.install_bound()
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), {
            "project-auditor", "project-continuous-repair"})
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(),
                         "gen-1")

    def test_rejects_a_real_verdict_copied_from_another_candidate(self):
        other = self._package(self.root / "generated-other", marker="otro")
        run = self._host_run(other, "gen-1")
        borrowed = self._host_verdict(run, other, "gen-1")
        # The candidate under installation is not the accepted one.
        (self.generated / "skills" / "project-check" /
         "resources" / "guide.txt").write_text("guide alterada\n")
        with self.assertRaisesRegex(
                (tx.TransactionError, ValueError), "cambió el candidato"):
            self.install_bound(verdict_path=borrowed)
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())
        self.assertTrue(borrowed.is_file())

    def test_rejects_a_real_verdict_from_another_generation(self):
        run = self._host_run(self.generated, "gen-2")
        borrowed = self._host_verdict(run, self.generated, "gen-2")
        with self.assertRaisesRegex(tx.TransactionError, "otra generación"):
            self.install_bound(generation="gen-1", verdict_path=borrowed)
        self.assertFalse((self.workspace / ".dsh-managed" / "ACTIVE").exists())

    def test_three_presets_are_packaged_with_implementer_and_legacy_two_still_activate(self):
        # The two-mode fixture below is a previous generation, not a cap.
        role = "implementer"
        preset_id = f"project-{role}"
        mode = self.generated / "modes" / preset_id
        mode.mkdir()
        layout = {"session_root": self.root.name, "product_root": "Syncify",
                  "workspace_root": "Syncify-workspace",
                  "state_root": "Syncify-workspace/mode-state"}
        lifecycle = expected_lifecycle(role, layout)
        (mode / "mode.json").write_text(json.dumps({
            "preset_id": preset_id, "role": role, "reads": [layout["product_root"]],
            "writes": [layout["state_root"]], "mode_lifecycle": lifecycle}) + "\n")
        (mode / "preset.yml").write_text(f"name: {preset_id}\n")
        (mode / "agent.cordis.yml").write_text(mode_composition(preset_id))
        (mode / "SKILL.md").write_text(
            f"---\nname: {preset_id}\ndescription: implementer mode\n---\n"
            f"# {preset_id}\n```json mode-layout\n"
            f"{json.dumps(layout, separators=(',', ':'))}\n```\n"
            f"```json mode-lifecycle\n"
            f"{json.dumps(lifecycle, separators=(',', ':'))}\n```\n")
        self.client = Client(ids=("project-auditor", "project-continuous-repair",
                                  preset_id))
        result = self.install(client=self.client)
        self.assertEqual(result["result"], "ACTIVE")
        self.assertEqual(set(result["published_presets"]), set(self.client.ids))
        receipt = json.loads((self.workspace / ".dsh-managed" /
                              "published-presets.json").read_text())
        bundle = Path(receipt["bundle_path"])
        self.assertTrue((bundle / "skills" / preset_id / "SKILL.md").is_file())
        self.assertIn(f"preset-{preset_id}", (bundle / "cordis.patch.yml").read_text())

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
        self.assertEqual(patch.count("sampleOverCapGlobResults: false"), 2)
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
        self.assertEqual(descriptor["product_root"], "Syncify")
        self.assertEqual(descriptor["state_root"], "Syncify-workspace/mode-state")
        state_schema = json.loads(
            (self.workspace / "mode-state" / "state-schema.json").read_text())
        self.assertEqual(state_schema["files"]["findings.jsonl"]["limit"], 200)
        work_items = json.loads(
            (self.workspace / "mode-state" / "work-items.json").read_text())
        self.assertEqual(work_items, {
            "schema_version": 1, "candidate": None, "items": []})
        lifecycle = json.loads((self.generated / "modes/project-auditor/mode.json").read_text())["mode_lifecycle"]
        self.assertEqual(
            lifecycle["startup"]["first_bash_command"],
            'set -eu; pwd; test "$(basename "$PWD")" = '
            f'{self.root.name} -a -d ./Syncify -a -d ./Syncify-workspace; '
            "printf '__IMPROVEMENT_LAYOUT_OK__\\n'")
        self.assertEqual(
            lifecycle["startup"]["success_sentinel"],
            "__IMPROVEMENT_LAYOUT_OK__")
        self.assertEqual((self.workspace / ".dsh-managed" / "ACTIVE").read_text().strip(), "gen-1")
        capability_path = (self.workspace / stack.PLAN_RELATIVE)
        self.assertTrue(capability_path.is_file())
        capability_plan = stack.load(self.workspace)
        self.assertEqual(capability_plan["stacks"], [])
        self.assertEqual(result["capability_plan"]["path"], str(capability_path))
        self.assertEqual(result["capability_plan"]["stacks"], [])
        self.assertEqual(result["capability_plan"]["evidence"],
                         "product-own-entrypoint-only")
        self.assertEqual(result["capability_plan"]["stubs"],
                         "investigation-material-never-verification-evidence")

    def test_install_archives_legacy_mode_evidence_outside_active_state(self):
        state = self.workspace / "mode-state"
        state.mkdir()
        original = b"legacy check output\x00\n"
        (state / "a01-check-red.txt").write_bytes(original)

        self.install()

        archives = list((self.workspace / ".dsh-managed" /
                         "mode-state-legacy").iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / "files" /
                          "a01-check-red.txt").read_bytes(), original)
        receipt = json.loads((archives[0] / "receipt.json").read_text())
        self.assertEqual(receipt["state_root"],
                         "Syncify-workspace/mode-state")
        self.assertEqual(receipt["files"][0]["name"],
                         "a01-check-red.txt")
        self.assertFalse((state / "a01-check-red.txt").exists())
        self.assertTrue((state / "project.json").is_file())

    def test_direct_transaction_rejects_wrong_cased_layout(self):
        skill = self.generated / "modes/project-auditor/SKILL.md"
        skill.write_text(skill.read_text().replace(
            "Syncify-workspace/mode-state", "syncify-workspace/mode-state"))
        with self.assertRaisesRegex(tx.TransactionError, "mode-layout must equal"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_transaction_rejects_missing_lifecycle(self):
        mode_path = self.generated / "modes/project-auditor/mode.json"
        mode = json.loads(mode_path.read_text())
        del mode["mode_lifecycle"]
        mode_path.write_text(json.dumps(mode) + "\n")
        with self.assertRaisesRegex(tx.TransactionError, "mode_lifecycle"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_transaction_rejects_incomplete_composition(self):
        composition = self.generated / "modes/project-auditor/agent.cordis.yml"
        composition.write_text(
            "- id: persona\n  name: '@deepseek-ai/dsh-persona'\n")
        with self.assertRaisesRegex(tx.TransactionError, "preset bootstrap contract"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_direct_transaction_rejects_prohibited_composition(self):
        composition = self.generated / "modes/project-auditor/agent.cordis.yml"
        composition.write_text(mode_composition("project-auditor") +
            "- id: workflow\n  name: '@deepseek-ai/dsh-tool-workflow'\n")
        with self.assertRaisesRegex(tx.TransactionError, "prohibited plugin rows"):
            self.install()
        self.assertFalse((self.workspace / ".dsh-managed").exists())

    def test_router_selects_only_host_accepted_installed_skill_and_abstains(self):
        import skill_router
        skill = self.generated / "skills" / "project-check"
        routing = {"actions": ["implement"], "modes": ["implementador"],
                   "requires": {"language": "python"},
                   "capability_set": ["read_product"], "context_bytes": 100}
        contracts = self.generated / "contracts"
        contracts.mkdir()
        contract = {"schema_version": 1, "kind": "skill", "name": "project-check",
                    "motive": "test", "domain": ["test"], "reuse_source": "composition",
                    "inputs": [], "outputs": [], "required_capabilities": [],
                    "forbidden_capabilities": [], "files": [
                        {"path": "SKILL.md", "type": "skill-entrypoint"}],
                    "behavior_test": "test", "provenance": {"license": "MIT"},
                    "routing": routing}
        (contracts / "project-check.skill.json").write_text(json.dumps(contract) + "\n")
        manifest_path = self.generated / "generation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["effective_routing_digest"] = skill_router._digest(
            [("project-check", routing)])
        manifest_path.write_text(json.dumps(manifest) + "\n")
        instance = tx.Transaction(self.workspace, dsh_home=self.home, client=Client())
        observations = [{"fact": "language", "value": "python",
                         "evidence_sha256": "a" * 64}]
        self.assertEqual(instance.select_project_skills(
            observations, {"action": "implement"}, mode="implementador",
            budget=200)["abstain"], "no_active_generation")
        self.install(client=instance.client)
        selected = instance.select_project_skills(
            observations, {"action": "implement"}, mode="implementador",
            budget=200)
        self.assertEqual(selected["allowed"], ["project-check"])
        self.assertFalse(selected["scope"]["authorizes_execution"])
        self.assertEqual(instance.select_project_skills(
            observations, {"action": "implement"}, mode="implementador",
            budget=20)["abstain"], "context_budget_exceeded")
        self.assertEqual(instance.select_project_skills(
            observations, {"action": "implement"}, mode="implementador",
            budget=200, denied=["project-check"])["abstain"],
            "no_eligible_skill")
        # A bundled skill changed after publication cannot be selected.
        (instance.install_root / "bundles/gen-1/skills/project-check/resources/guide.txt").write_text("tampered\n")
        self.assertEqual(instance.select_project_skills(
            observations, {"action": "implement"}, mode="implementador",
            budget=200)["abstain"], "bundle_not_confirmed")

    def test_bundle_contains_scoped_anti_escalation_plugin(self):
        self.install()
        plugin = self.client.active_bundle / "anti-escalation.mjs"
        self.assertTrue(plugin.is_file())
        patch = (self.client.active_bundle / "cordis.patch.yml").read_text()
        self.assertEqual(patch.count(str(plugin.resolve())), 2)
        self.assertNotIn("name: './anti-escalation.mjs'", patch)

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

    def test_idempotent_result_keeps_both_published_presets(self):
        first = self.install()
        second = self.install(client=self.client)
        self.assertEqual(first["published_presets"], second["published_presets"])
        self.assertEqual(second["result"], "NO_OP")
        self.assertEqual(len(second["published_presets"]), 2)

    def test_campaign_plan_private_and_empty_stacks_never_claim_pass(self):
        result = self.install()
        receipt = result['campaign_plan']
        self.assertTrue(receipt['written'])
        plan_path = Path(receipt['path'])
        self.assertEqual(plan_path, self.workspace / '.dsh-managed/campaign/plan.json')
        self.assertFalse((self.generated / 'campaign').exists())
        plan = json.loads(plan_path.read_bytes())
        self.assertEqual(len(plan['steps']), 8)
        manifest = json.loads(plan_path.with_name('manifest.json').read_bytes())
        self.assertEqual(manifest['stacks'], [])
        self.assertEqual(manifest['campaign_plan_sha256'], receipt['campaign_plan_sha256'])
        self.assertEqual(
            [step['id'] for step in plan['steps'] if step['type'] == 'gate'
             and step['on_fail']['action'] == 'abort'],
            ['preflight', 'verificar-final', 'cerrar'])
        import campaign
        # Sin stacks ni ledger no hay PASS de verificación: solo cerrar es un
        # paso terminal sin entrada de verificación.
        code, verdict = campaign.verification_verdict(self.workspace, 'pre')
        self.assertNotEqual(code, campaign.EXIT_PASS)
        self.assertNotEqual(verdict['verdict'], 'PASS')

    def test_restart_required_campaign_pendiente_sin_fichero(self):
        result = self.install(client=Client(application='restart-required'))
        self.assertEqual(result['result'], 'RESTART_REQUIRED')
        self.assertEqual(result['campaign_plan']['state'], 'pendiente-de-activacion')
        self.assertEqual(result['campaign_plan']['preset_ids'],
                         ['project-auditor', 'project-continuous-repair'])
        self.assertFalse((self.workspace / '.dsh-managed/campaign').exists())

    def test_no_op_materializa_y_preserva_mtime(self):
        self.install()
        plan = self.workspace / '.dsh-managed/campaign/plan.json'
        plan.unlink()
        first = self.install(client=self.client)
        self.assertEqual(first['result'], 'NO_OP')
        self.assertTrue(first['campaign_plan']['written'])
        mtime = plan.stat().st_mtime_ns
        second = self.install(client=self.client)
        self.assertEqual(second['result'], 'NO_OP')
        self.assertFalse(second['campaign_plan']['written'])
        self.assertEqual(plan.stat().st_mtime_ns, mtime)

    def test_rollback_restores_capability_and_campaign_absent_or_bytes(self):
        for old_state in ('absent', 'present'):
            with self.subTest(old_state=old_state):
                # Una instalación nueva por caso permite probar también el
                # marcador de ausencia sin residuos de la primera ejecución.
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    workspace = root / 'Syncify-workspace'
                    workspace.mkdir()
                    product = root / 'Syncify'
                    product.mkdir()
                    (workspace / 'project.json').write_text(json.dumps({
                        'schema': 1, 'name': 'project', 'project': str(product)}) + '\n')
                    # _package usa self.root para el session_root; en este
                    # subTest lo vinculamos al nuevo /tmp hasta que termine.
                    prior_root = self.root
                    self.root = root
                    try:
                        generated = self._package(root / 'generated')
                    finally:
                        self.root = prior_root
                    home = root / 'home'
                    if old_state == 'present':
                        managed = workspace / '.dsh-managed'
                        campaign_dir = managed / 'campaign'
                        campaign_dir.mkdir(parents=True)
                        (managed / 'capability-plan.json').write_bytes(b'viejo plan\n')
                        (campaign_dir / 'plan.json').write_bytes(b'vieja campana\n')
                    previous_plan = (workspace / '.dsh-managed/capability-plan.json')
                    previous_campaign = (workspace / '.dsh-managed/campaign/plan.json')
                    old_plan = previous_plan.read_bytes() if previous_plan.exists() else None
                    old_campaign = previous_campaign.read_bytes() if previous_campaign.exists() else None
                    transaction = tx.Transaction(workspace, dsh_home=home,
                                                 client=Client())
                    host_verdict = root / 'host-verdict.json'
                    host_verdict.write_text(json.dumps(verdict()) + '\n')
                    # El fallo después de ACTIVE obliga al except a restaurar
                    # capacidad y campaña sin perder los bytes anteriores.
                    with unittest.mock.patch('acceptance.validate_host_verdict',
                                             return_value=verdict()):
                        with unittest.mock.patch.object(tx, 'write_campaign',
                                                       side_effect=RuntimeError('fallo tras ACTIVE')):
                            with self.assertRaisesRegex(RuntimeError, 'fallo tras ACTIVE'):
                                transaction.install(generated, 'gen-1',
                                                    host_verdict=host_verdict)
                    self.assertEqual(previous_plan.read_bytes() if previous_plan.exists() else None,
                                     old_plan)
                    self.assertEqual(previous_campaign.read_bytes()
                                     if previous_campaign.exists() else None, old_campaign)

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
            "/usr/bin/python3", "-B", str(ROOT / "scripts" / "transaction.py"),
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
