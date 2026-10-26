"""Campaign UX regressions: project default, progress feedback, budget knob.

    python3 -B -m unittest tests.test_campaign_ux -v

These pin the three defects of the first real manual campaign on Syncify
(2026-10-25, run ``gen-c34a3d00cce3``):

* D-03 — ``--project`` was required even though the documented layout clones
  the framework beside the project, so the obvious default was never derived.
* D-02 — ``install`` printed nothing until the final JSON: an operator could
  not tell a working run from a hung one.
* D-01 — the Creator token ceiling (500000) was hardcoded with no CLI knob,
  and the RETAINED message named no retry action.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap
import creator_client as cc


def _git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True,
                   stdout=subprocess.DEVNULL)


def _progress_on():
    """Enable human progress, returning the previous setting to restore.

    Other suite modules silence progress at import time (module-level
    ``IMPROVEMENT_QUIET=1`` in the shared process), so a regression that
    needs the real output has to lift the flag itself and put back whatever
    was there for the modules that run after it.
    """
    saved = os.environ.get("IMPROVEMENT_QUIET")
    os.environ.pop("IMPROVEMENT_QUIET", None)
    return saved


def _restore_progress(saved):
    if saved is None:
        os.environ.pop("IMPROVEMENT_QUIET", None)
    else:
        os.environ["IMPROVEMENT_QUIET"] = saved


class ProjectDefault(unittest.TestCase):
    """D-03: omitted --project resolves the single sibling checkout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.framework = self.parent / "Improvement"
        _git_init(self.framework)

    def test_single_sibling_resolves(self):
        project = self.parent / "Syncify"
        _git_init(project)
        (project / "main.py").write_text("print('ok')\n")
        resolved = bootstrap._resolve_project_argument(
            None, framework=self.framework)
        self.assertEqual(resolved, project.resolve())

    def test_zero_siblings_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            bootstrap._resolve_project_argument(
                None, framework=self.framework)
        self.assertIn("pasa --project", str(ctx.exception))

    def test_several_siblings_fail_closed_naming_them(self):
        for name in ("Syncify", "RehabWeb"):
            _git_init(self.parent / name)
        with self.assertRaises(ValueError) as ctx:
            bootstrap._resolve_project_argument(
                None, framework=self.framework)
        self.assertIn("pasa --project", str(ctx.exception))
        self.assertIn("Syncify", str(ctx.exception))
        self.assertIn("RehabWeb", str(ctx.exception))

    def test_explicit_value_wins_over_siblings(self):
        elsewhere = self.parent / "otro-lugar"
        elsewhere.mkdir()
        (elsewhere / "x.py").write_text("")
        for name in ("Syncify", "RehabWeb"):
            _git_init(self.parent / name)
        resolved = bootstrap._resolve_project_argument(
            str(elsewhere), framework=self.framework)
        self.assertEqual(resolved, elsewhere.resolve())

    def test_workspace_and_hidden_dirs_are_not_candidates(self):
        _git_init(self.parent / "Syncify-workspace")
        _git_init(self.parent / ".oculto")
        with self.assertRaises(ValueError):
            bootstrap._resolve_project_argument(
                None, framework=self.framework)


class ProgressFeedback(unittest.TestCase):
    """D-02: human progress on stderr; stdout stays machine-readable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.workspace = self.root / "workspace"

    def test_install_emits_progress_lines_on_stderr(self):
        self.addCleanup(_restore_progress, _progress_on())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = bootstrap.install(self.project, self.workspace)
        self.assertEqual(result["result"], "CREATED")
        lines = [l for l in err.getvalue().splitlines() if l]
        self.assertTrue(lines, "install no emitió ninguna línea de progreso")
        self.assertTrue(all(l.startswith("[") for l in lines),
                        f"las líneas de progreso llevan timestamp: {lines}")
        joined = "\n".join(lines)
        self.assertIn("preflight", joined)
        self.assertIn(result["generation_id"], joined)
        self.assertIn("techo Creator", joined)

    def test_improvement_quiet_silences_progress(self):
        err = io.StringIO()
        # A real copy: ``old = os.environ`` would alias the same object and
        # the clear() below would wipe the "backup" too, leaving the whole
        # process without an environment for every later test.
        old = dict(os.environ)
        os.environ["IMPROVEMENT_QUIET"] = "1"
        try:
            with contextlib.redirect_stderr(err):
                bootstrap.install(self.project, self.workspace)
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertEqual(err.getvalue(), "")

    def test_supervision_ticks_report_tokens_and_cancel(self):
        self.addCleanup(_restore_progress, _progress_on())
        with contextlib.redirect_stderr(io.StringIO()):
            run_dir = Path(bootstrap.install(self.project,
                                             self.workspace)["run_dir"])
        session = cc.CreatorSession(run_dir, max_tokens=100)
        state, _ = cc._load_or_create_session_state(
            run_dir, session.prepare(),
            json.loads((run_dir / "run.json").read_text()),
            now_fn=lambda: 1000.0)

        def fake_observe(client, st):
            # One real assistant/message usage record over the ceiling, in
            # the same shape _observe_creator returns from DSH.
            return {"cursor": 1, "running": False, "children": [], "jobs": [],
                    "events": [{"seq": 1, "type": "assistant/message",
                                "data": {"turn": 1, "step": 1,
                                         "usage": {
                                             "inputTokens": 60,
                                             "outputTokens": 10,
                                             "cacheReadTokens": 50,
                                             "totalTokens": 120}}}]}

        class FakeClient:
            def cancel_session(self, session_id):
                pass

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with unittest.mock.patch.object(cc, "_observe_creator", fake_observe):
                outcome = cc._supervise_creator(
                    session, FakeClient(), state,
                    now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
        self.assertEqual(outcome["result"], "RETAINED")
        joined = err.getvalue()
        self.assertIn("120/100 tokens", joined)
        self.assertIn("cancelando sesión", joined)
        self.assertIn("quiescente", joined)


class BudgetKnob(unittest.TestCase):
    """D-01: --creator-max-tokens reaches run.json; RETAINED names the retry."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")

    def test_cli_flag_sets_run_budget(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "bootstrap.py"),
             "install", "--project", str(self.project),
             "--creator-max-tokens", "12345", "--no-dispatch"],
            capture_output=True, text=True, env=env, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        run_dir = Path(payload["run_dir"])
        budget = json.loads((run_dir / "run.json").read_text())["budget"]
        self.assertEqual(budget["max_tokens"], 12345)
        self.assertEqual(budget["max_attempts"], 3)
        self.assertEqual(budget["max_seconds"], 1800)

    def test_default_budget_unchanged_without_flag(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "bootstrap.py"),
             "install", "--project", str(self.project), "--no-dispatch"],
            capture_output=True, text=True, env=env, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        run_dir = Path(payload["run_dir"])
        budget = json.loads((run_dir / "run.json").read_text())["budget"]
        self.assertEqual(budget["max_tokens"], 500000)

    def test_retained_by_budget_message_names_retry_action(self):
        result = {"generation_id": "gen-x", "message": "Run gen-x creado",
                  "result": "CREATED"}
        run_dir = self.root / "run"
        run_dir.mkdir()
        retained = {"result": "RETAINED", "generation_id": "gen-x",
                    "reason": ("Límite de tokens Creator excedido: 523971 >= "
                               "500000; cancelación confirmada y sesión "
                               "quiescente")}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with unittest.mock.patch.object(
                    cc, "run_creator", return_value=retained):
                bootstrap._dispatch_creator_chain(
                    result, run_dir, launch_dsh=False, finalize_host=True)
        self.assertIn("--creator-max-tokens", result["message"])
        # The retained reason reaches the composed message: the operator
        # reads one line, not two documents.
        self.assertIn("523971 >= 500000", result["message"])

    def test_retained_other_cause_gets_no_budget_hint(self):
        result = {"generation_id": "gen-x", "message": "Run gen-x creado",
                  "result": "CREATED"}
        run_dir = self.root / "run"
        run_dir.mkdir()
        retained = {"result": "RETAINED", "generation_id": "gen-x",
                    "reason": "Creator terminó sin generation-manifest.json"}
        with contextlib.redirect_stderr(io.StringIO()):
            with unittest.mock.patch.object(
                    cc, "run_creator", return_value=retained):
                bootstrap._dispatch_creator_chain(
                    result, run_dir, launch_dsh=False, finalize_host=True)
        self.assertNotIn("--creator-max-tokens", result["message"])


class DshHomeEvidence(unittest.TestCase):
    """D-05: a DSH 0.2.1 home is a DSH home even without settings.yaml.

    The launch path used to demand settings.yaml/settings.yaml.imported and
    rejected the real 0.2.1-rc.2 home — configuration lives in
    ``profiles/web/cordis.patch.yml`` and credentials in ``.credentials.yaml``
    — stranding run ``gen-4f6e9fd18808`` PREPARED with DSH already launched
    and authenticated (campaign 2026-10-25).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "dsh-home"

    def _marker(self, *paths):
        self.home.mkdir(parents=True, exist_ok=True)
        for rel in paths:
            p = self.home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# marker\n")
        return cc._dsh_home_evidence(self.home)

    def test_legacy_settings_yaml_is_evidence(self):
        self.assertEqual(self._marker("settings.yaml"), "settings.yaml")

    def test_legacy_imported_settings_is_evidence(self):
        self.assertEqual(self._marker("settings.yaml.imported"),
                         "settings.yaml.imported")

    def test_dsh_021_credentials_are_evidence(self):
        # The campaign case: a 0.2.1 home carries no settings.yaml at all.
        self.assertEqual(self._marker(".credentials.yaml", ".anonymous-user-id"),
                         ".credentials.yaml")

    def test_dsh_021_profile_patch_is_evidence(self):
        marker = self._marker("profiles/web/cordis.yml",
                              "profiles/web/cordis.patch.yml",
                              "profiles/web/package.json")
        self.assertEqual(marker, "profiles/web/cordis.yml")

    def test_empty_home_is_not_evidence(self):
        self.home.mkdir(parents=True)
        self.assertIsNone(cc._dsh_home_evidence(self.home))

    def test_unrelated_files_are_not_evidence(self):
        self.assertIsNone(self._marker("readme.txt", "otra-cosa.json"))


class CancelKeepsPrimaryReason(unittest.TestCase):
    """D-07: a cancel-time usage-less message must not mask the real cause.

    Run ``gen-7df8fb95ba62`` (campaign 2026-10-25) exceeded its budget, the
    supervisor cancelled the session, and DSH flushed the in-flight assistant
    message without usage. The fold refused the account and the run was
    retained as "coste real desconocido" — hiding the actionable budget
    cause that was already measured (531771 >= 500000).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.run_dir = Path(
            bootstrap.install(self.project, self.root / "workspace")["run_dir"])

    def test_budget_reason_survives_a_usage_less_cancel_tail(self):
        session = cc.CreatorSession(self.run_dir, max_tokens=100)
        state, _ = cc._load_or_create_session_state(
            self.run_dir, session.prepare(),
            json.loads((self.run_dir / "run.json").read_text()),
            now_fn=lambda: 1000.0)
        calls = {"n": 0}

        def fake_observe(client, st):
            calls["n"] += 1
            if calls["n"] == 1:
                # Before the cancel: a clean account already over the ceiling.
                return {"cursor": 1, "running": True, "children": [],
                        "jobs": [],
                        "events": [
                            {"seq": 1, "type": "assistant/message",
                             "data": {"turn": 1, "step": 1,
                                      "usage": {"inputTokens": 60,
                                                "outputTokens": 10,
                                                "cacheReadTokens": 50,
                                                "totalTokens": 120}}}]}
            # After the cancel: DSH flushes the truncated in-flight step,
            # whose assistant/message carries no usage key at all.
            return {"cursor": 3, "running": False, "children": [], "jobs": [],
                    "events": [
                        {"seq": 2, "type": "assistant/message",
                         "data": {"turn": 1, "step": 2}},
                        {"seq": 3, "type": "turn/end",
                         "data": {"turn": 1,
                                  "reason": {"kind": "aborted",
                                             "reason": {"kind": "user"}}}},
                    ]}

        class FakeClient:
            def cancel_session(self, session_id):
                pass

        err = io.StringIO()
        self.addCleanup(_restore_progress, _progress_on())
        with contextlib.redirect_stderr(err):
            with unittest.mock.patch.object(cc, "_observe_creator", fake_observe):
                outcome = cc._supervise_creator(
                    session, FakeClient(), state,
                    now_fn=lambda: 1000.0, sleep_fn=lambda s: None)
        self.assertEqual(outcome["result"], "RETAINED")
        reason = outcome["reason"]
        # The primary, actionable cause leads; the unmeasurable tail is a
        # note, never a replacement.
        self.assertIn("Límite de tokens Creator excedido: 120 >= 100", reason)
        self.assertIn("cola de cancelación sin usage medible", reason)


if __name__ == "__main__":
    unittest.main()
