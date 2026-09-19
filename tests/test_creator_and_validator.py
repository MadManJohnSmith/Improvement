"""Tests C2 Creator automation y C3 Host validator.

    python3 -B -m unittest tests.test_creator_and_validator -v
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap
import creator_client as cc
import host_validator as hv


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.workspace = self.root / "workspace"
        result = bootstrap.install(self.project, self.workspace)
        self.run_dir = Path(result["run_dir"])
        self.gen_id = result["generation_id"]

    def make_package(self, *, status="GENERATED", extra=None):
        generated = self.run_dir / "generated"
        skill = generated / "skills" / "project-auditor"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Auditor\n")
        artifacts = [{
            "path": "skills/project-auditor/SKILL.md",
            "type": "skill-entrypoint",
            "sha256": cc._digest_bytes(b"# Auditor\n"),
        }]
        manifest = {
            "schema_version": 1,
            "generation_id": self.gen_id,
            "status": status,
            "project": {"name": "project", "root_identity": "a" * 64,
                        "base_revision": "rev"},
            "creator": {"session_ref": "session", "runtime_version": "1"},
            "framework": {"revision": "framework"},
            "artifacts": artifacts,
            "required_capabilities": [],
            "forbidden_capabilities": [],
            "effective_routing_digest": "b" * 64,
            "context_policy": {"skill_entrypoint_max_bytes": 32768,
                               "support_file_max_bytes": 24576,
                               "warning_ratio": 0.9},
            "license_provenance": [],
        }
        if extra:
            manifest.update(extra)
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        return generated, manifest


class CreatorTransportTests(unittest.TestCase):
    def test_extracts_token_url_without_persisting_it(self):
        client = cc.DshLocalClient.from_console_line(
            "dsh web: http://127.0.0.1:3080/?token=runtime-only-token"
        )
        self.assertFalse(client.authenticated)
        self.assertEqual(client.base_url, "http://127.0.0.1:3080")

    def test_exchanges_token_for_cookie(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.endswith("token=runtime-only-token"):
                    self.send_response(200)
                    self.send_header("Set-Cookie", "dsh-auth-test=opaque; Path=/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"{}")
            def log_message(self, *_args):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        client = cc.DshLocalClient.from_console_line(
            f"dsh web: http://127.0.0.1:{port}/?token=runtime-only-token"
        )
        client.exchange_token()
        self.assertTrue(client.authenticated)

    def test_from_dsh_home_generates_valid_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            dsh_home = Path(tmp)
            (dsh_home / ".credentials.yaml").write_text(
                "records:\n"
                "  client-connection/browser-session:\n"
                "    payload:\n"
                "      secret: " + ("a" * 32) + "\n"
            )
            client = cc.DshLocalClient.from_dsh_home(str(dsh_home), port=3080)
            self.assertTrue(client.authenticated)
            self.assertIn("dsh-auth-", client._cookie)


class CreatorTests(Base):
    def test_prepare_builds_prompt_and_request(self):
        session = cc.CreatorSession(self.run_dir)
        result = session.prepare()
        self.assertEqual(result["generation_id"], self.gen_id)
        self.assertTrue((self.run_dir / "creator-prompt.md").is_file())
        req = json.loads((self.run_dir / "generation-request.json").read_text())
        self.assertEqual(req["prompt_version"], cc.PROMPT_VERSION)
        self.assertEqual(req["skill_selection_order"][0], "base-library")

    def test_prepare_updates_status(self):
        cc.CreatorSession(self.run_dir).prepare()
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "GENERATING")

    def test_run_creator_without_output_prepared(self):
        result = cc.run_creator(self.run_dir)
        self.assertEqual(result["result"], "PREPARED")

    def test_acquire_dsh_client_fails_closed_without_session(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}):
            client, origin = cc.acquire_dsh_client()
        self.assertIsNone(client)
        self.assertIn("dsh web", origin)

    def test_run_creator_acquires_client_when_asked(self):
        class MockClient:
            authenticated = True
            def __init__(self):
                self.prompts = []
            def create_creator_session(self, *, cwd, agent_preset=None):
                return "acquired-session"
            def send_prompt(self, session_id, prompt):
                self.prompts.append((session_id, prompt))
                return {"ok": True}
        mock = MockClient()
        with unittest.mock.patch.object(
                cc, "acquire_dsh_client", return_value=(mock, "test-home")):
            result = cc.run_creator(self.run_dir, acquire=True, wait=False)
        self.assertEqual(result["result"], "PREPARED")
        self.assertEqual(result["dsh_session_id"], "acquired-session")
        self.assertEqual(result["dsh_origin"], "test-home")
        self.assertEqual(len(mock.prompts), 1)

    def test_run_creator_with_authenticated_client_dispatches_prompt(self):
        class MockClient:
            authenticated = True
            def __init__(self):
                self.prompts = []
            def create_creator_session(self, *, cwd, agent_preset=None):
                return "mock-session-123"
            def send_prompt(self, session_id, prompt):
                self.prompts.append((session_id, prompt))
                return {"ok": True}
        mock = MockClient()
        result = cc.run_creator(self.run_dir, client=mock, wait=False)
        self.assertEqual(result["result"], "PREPARED")
        self.assertEqual(result["dsh_session_id"], "mock-session-123")
        self.assertEqual(len(mock.prompts), 1)
        self.assertIn("mock-session-123", mock.prompts[0][0])

    def test_generation_output_requires_generated_status(self):
        generated, _ = self.make_package(status="ACTIVE")
        session = cc.CreatorSession(self.run_dir)
        with self.assertRaises(ValueError):
            session.verify_generation_output()

    def test_generation_output_rejects_absolute_path(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["path"] = "/etc/passwd"
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        with self.assertRaises(ValueError):
            cc.CreatorSession(self.run_dir).verify_generation_output()

    def test_retain_marks_run(self):
        session = cc.CreatorSession(self.run_dir)
        result = session.retain("missing provider")
        self.assertEqual(result["result"], "RETAINED")
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RETAINED")

    def test_prompt_contains_invariants(self):
        session = cc.CreatorSession(self.run_dir)
        session.prepare()
        prompt = (self.run_dir / "creator-prompt.md").read_text()
        self.assertIn("base-library", prompt)
        self.assertIn("no proveedores/modelos/routing nuevos", prompt.lower())
        self.assertIn("bootstrap.py accept", prompt)

    def test_prompt_embeds_materialized_library(self):
        """The versioned prompt lists the real base skills and catalog gates."""
        session = cc.CreatorSession(self.run_dir)
        session.prepare()
        prompt = (self.run_dir / "creator-prompt.md").read_text()
        self.assertIn("## Biblioteca disponible", prompt)
        self.assertIn("**Digest de biblioteca:**", prompt)
        self.assertIn("`systematic-debugging`", prompt)
        self.assertIn("`fastapi-openapi-contract-check`", prompt)
        self.assertIn("activar si: fastapi o pydantic declarados", prompt)
        self.assertIn("reuse_reference", prompt)

    def test_all_five_prompt_types_build_successfully(self):
        run_doc = json.loads((self.run_dir / "run.json").read_text())
        proj_manifest = {"base_revision": "rev-test"}
        idx = {"entries": []}
        for ptype in cc.PROMPT_TYPES:
            prompt = cc.build_creator_prompt(
                self.run_dir, run_doc, proj_manifest, idx,
                prompt_type=ptype,
                context={"reason": "test retention", "skill_name": "test-skill"},
            )
            self.assertIn(ptype, prompt)
            self.assertIn("Invariantes", prompt)


def _write_dsh_home(home, *, provider="testprov", api_key_env="TEST_PROV_KEY",
                    models=2, default_provider=None, extra_providers=()):
    """Fixture DSH home: credentials plus a structural settings.yaml."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / ".credentials.yaml").write_text(
        "records:\n"
        "  client-connection/browser-session:\n"
        "    payload:\n"
        "      secret: " + ("a" * 32) + "\n"
    )
    models_yaml = "".join(
        f"        - id: model-{i}\n          name: Model {i}\n"
        for i in range(models))
    provider_block = ""
    if provider:
        provider_block = f"    {provider}:\n"
        if api_key_env:
            provider_block += f"      apiKeyEnv: {api_key_env}\n"
        provider_block += f"      models:\n{models_yaml}"
    for name, env_name, count in extra_providers:
        provider_block += f"    {name}:\n"
        if env_name:
            provider_block += f"      apiKeyEnv: {env_name}\n"
        provider_block += "      models:\n" + "".join(
            f"        - id: {name}-model-{i}\n          name: M{i}\n"
            for i in range(count))
    (home / "settings.yaml").write_text(
        "agent-default-model:\n"
        f"  provider: {default_provider or provider or 'none'}\n"
        "  model: model-0\n"
        "llm-pi-ai:\n"
        "  providers:\n"
        f"{provider_block}"
    )
    return home


class DshLifecycleTests(unittest.TestCase):
    """Ciclo de vida DSH: instancias previas y puerta de llave API."""

    def test_provider_status_ok_with_key_in_env(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}):
            home = _write_dsh_home(tmp)
            status = cc.dsh_provider_status(home)
        self.assertTrue(status["ok"])
        self.assertEqual(status["provider"], "testprov")
        self.assertEqual(status["api_key_env"], "TEST_PROV_KEY")

    def test_provider_status_falls_back_when_default_key_missing(self):
        """The default provider's key is not required: any usable one wins."""
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"TEST_PROV_KEY": ""}), \
                unittest.mock.patch.dict(os.environ, {"PROV_B_KEY": "x"}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]):
            home = _write_dsh_home(
                tmp, extra_providers=[("prov-b", "PROV_B_KEY", 1)])
            status = cc.dsh_provider_status(home)
        self.assertTrue(status["ok"])
        self.assertEqual(status["provider"], "prov-b")
        self.assertEqual(status["source"], "fallback")
        self.assertIn("llave TEST_PROV_KEY ausente", str(status["skipped"]))

    def test_provider_status_stops_when_no_provider_is_usable(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"TEST_PROV_KEY": ""}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]):
            home = _write_dsh_home(tmp)
            status = cc.dsh_provider_status(home)
        self.assertFalse(status["ok"])
        self.assertIn("ningún proveedor utilizable", status["reason"])
        self.assertIn("TEST_PROV_KEY", status["reason"])

    def test_provider_status_ignores_unknown_default_and_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}):
            home = _write_dsh_home(tmp, default_provider="ghost")
            status = cc.dsh_provider_status(home)
        self.assertTrue(status["ok"])
        self.assertEqual(status["provider"], "testprov")
        self.assertEqual(status["source"], "fallback")

    def test_provider_status_fails_without_models(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}):
            home = _write_dsh_home(tmp, models=0)
            status = cc.dsh_provider_status(home)
        self.assertFalse(status["ok"])
        self.assertIn("sin modelos", status["reason"])

    def test_find_dsh_pids_matches_only_dsh_web(self):
        fake = unittest.mock.Mock()
        fake.stdout = (
            f"{os.getpid()} python3 -B -m unittest tests\n"
            "4140 node /x/@deepseek-ai/dsh/lib/bin.js --profile web --port 3081\n"
            "68865 npm exec @deepseek-ai/dsh web\n"
            "12059 node /home/t/.npm/_npx/x/node_modules/.bin/dsh web\n"
            "70000 node /x/@deepseek-ai/dsh/lib/bin.js --profile audit\n"
        )
        with unittest.mock.patch.object(cc.subprocess, "run",
                                        return_value=fake):
            pids = cc._find_dsh_pids()
        self.assertEqual(pids, [4140, 68865, 12059])

    def test_dsh_web_cmdline_classifier(self):
        cases = {
            "node /home/t/.npm/_npx/x/node_modules/.bin/dsh web": True,
            "npm exec @deepseek-ai/dsh web": True,
            "node /x/@deepseek-ai/dsh/lib/bin.js --profile web --port 3081":
                True,
            "node /x/@deepseek-ai/dsh/lib/bin.js --profile audit": False,
            "python -m http.server 3080": False,
            "vim notes-dsh.txt": False,
        }
        for cmdline, expected in cases.items():
            with self.subTest(cmdline=cmdline):
                self.assertEqual(cc._is_dsh_web_cmdline(cmdline), expected)

    def test_stop_dsh_instances_signals_and_escalates(self):
        killed = []
        with unittest.mock.patch.object(cc, "_pid_alive",
                                        return_value=True), \
                unittest.mock.patch("os.kill",
                                    side_effect=lambda p, s: killed.append((p, s))):
            stopped = cc._stop_dsh_instances([4140, 68865], timeout=0)
        self.assertEqual(stopped, [4140, 68865])
        import signal
        self.assertIn((4140, signal.SIGTERM), killed)
        self.assertIn((4140, signal.SIGKILL), killed)

    def test_launch_path_stops_existing_and_gates_on_key(self):
        fake_client = unittest.mock.Mock()
        fake_client.authenticated = True
        fake_process = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}), \
                unittest.mock.patch.object(cc, "launch_dsh_web",
                                           return_value=(fake_process,
                                                         fake_client)):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client(launch=True)
        self.assertIs(client, fake_client)
        self.assertIn("launched:dsh-web", origin)
        self.assertIn("testprov", origin)
        fake_process.kill.assert_not_called()

    def test_launch_path_stops_running_instance_first(self):
        fake_client = unittest.mock.Mock()
        fake_client.authenticated = True
        fake_process = unittest.mock.Mock()
        stopped = []
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[68865]), \
                unittest.mock.patch.object(
                    cc, "_stop_dsh_instances",
                    side_effect=lambda pids, **k: stopped.extend(pids)), \
                unittest.mock.patch.object(cc, "launch_dsh_web",
                                           return_value=(fake_process,
                                                         fake_client)):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client(launch=True)
        self.assertEqual(stopped, [68865])
        self.assertIsNotNone(client)

    def test_launch_path_warns_and_proceeds_when_key_missing(self):
        """Env is not DSH's only key source: missing key warns, not blocks."""
        fake_client = unittest.mock.Mock()
        fake_client.authenticated = True
        fake_process = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ, {"TEST_PROV_KEY": ""}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]), \
                unittest.mock.patch.object(cc, "launch_dsh_web",
                                           return_value=(fake_process,
                                                         fake_client)):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client(launch=True)
        self.assertIs(client, fake_client)
        self.assertIn("aviso:", origin)
        self.assertIn("ningún proveedor utilizable", origin)
        self.assertIn("TEST_PROV_KEY", origin)
        fake_process.kill.assert_not_called()

    def test_launch_path_strict_mode_stops_when_key_missing(self):
        fake_client = unittest.mock.Mock()
        fake_client.authenticated = True
        fake_process = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ, {"TEST_PROV_KEY": ""}), \
                unittest.mock.patch.dict(os.environ,
                                         {"DSH_PROVIDER_STRICT": "1"}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]), \
                unittest.mock.patch.object(cc, "launch_dsh_web",
                                           return_value=(fake_process,
                                                         fake_client)):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client(launch=True)
        self.assertIsNone(client)
        self.assertIn("ningún proveedor utilizable", origin)
        fake_process.kill.assert_called_once()

class _FakeProcess:
    """Popen fake: poll() reflects exhaustion of stdout, like a real pipe."""

    def __init__(self, lines, exit_code=1):
        import io
        self._text = "".join(line + "\n" for line in lines)
        self.stdout = io.StringIO(self._text)
        self._exit = exit_code
        self.killed = False

    def poll(self):
        return self._exit if self.stdout.tell() >= len(self._text) else None

    def kill(self):
        self.killed = True


class LaunchDshWebTests(unittest.TestCase):
    """El lanzamiento captura la salida de DSH para diagnosticar fallos."""

    def test_launch_returns_client_on_url(self):
        proc = _FakeProcess([
            "starting dsh...",
            "dsh web: http://127.0.0.1:3080/?token=abc123",
        ], exit_code=0)
        with unittest.mock.patch.object(cc.subprocess, "Popen",
                                        return_value=proc):
            process, client = cc.launch_dsh_web()
        self.assertIs(process, proc)
        self.assertEqual(client.base_url, "http://127.0.0.1:3080")
        proc.killed is False

    def test_launch_failure_includes_captured_output(self):
        proc = _FakeProcess([
            "npm warn deprecated",
            "Ok to proceed? (y)",
            "npm error cancelled",
        ], exit_code=1)
        with unittest.mock.patch.object(cc.subprocess, "Popen",
                                        return_value=proc):
            with self.assertRaises(RuntimeError) as ctx:
                cc.launch_dsh_web()
        message = str(ctx.exception)
        self.assertIn("salida capturada", message)
        self.assertIn("Ok to proceed?", message)
        self.assertIn("exit=1", message)
        self.assertTrue(proc.killed)

    def test_launch_failure_redacts_tokens_in_output(self):
        proc = _FakeProcess([
            "connecting ?token=SECRETVALUE",
            "exited unexpectedly",
        ], exit_code=1)
        with unittest.mock.patch.object(cc.subprocess, "Popen",
                                        return_value=proc):
            with self.assertRaises(RuntimeError) as ctx:
                cc.launch_dsh_web()
        message = str(ctx.exception)
        self.assertNotIn("SECRETVALUE", message)
        self.assertIn("token=<redacted>", message)


    def test_port_listener_pid_parses_ss(self):
        fake = unittest.mock.Mock()
        fake.stdout = (
            "State  Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "LISTEN 0      511        127.0.0.1:3080      0.0.0.0:*     "
            'users:(("node",pid=4140,fd=18))\n'
            "LISTEN 0      511            [::]:9090           [::]:*     "
            'users:(("app",pid=99,fd=5))\n'
        )
        with unittest.mock.patch.object(cc.subprocess, "run",
                                        return_value=fake):
            pid, _line = cc._port_listener_pid(3080)
        self.assertEqual(pid, 4140)

    def test_ensure_port_free_when_no_listener(self):
        with unittest.mock.patch.object(
                cc, "_port_listener_pid", return_value=(None, "")):
            self.assertIsNone(cc._ensure_port_free_for_dsh(3080))

    def test_ensure_port_stops_lingering_dsh_listener(self):
        listener = [(4140, ""), (4140, ""), (None, "")]
        with unittest.mock.patch.object(
                cc, "_port_listener_pid",
                side_effect=lambda port: listener.pop(0)), \
                unittest.mock.patch.object(
                    cc, "_cmdline_of",
                    return_value="node /x/@deepseek-ai/dsh/lib/bin.js web"), \
                unittest.mock.patch.object(cc.time, "sleep"), \
                unittest.mock.patch.object(
                    cc, "_stop_dsh_instances",
                    side_effect=lambda pids, **k: None) as stop:
            self.assertIsNone(cc._ensure_port_free_for_dsh(3080))
        self.assertEqual(stop.call_args_list,
                         [unittest.mock.call([4140]),
                          unittest.mock.call([4140])])

    def test_ensure_port_stops_npx_bin_dsh_listener(self):
        """The tardis failure: .bin/dsh web carries no scope in its path."""
        listener = [(12059, ""), (None, "")]
        with unittest.mock.patch.object(
                cc, "_port_listener_pid",
                side_effect=lambda port: listener.pop(0)), \
                unittest.mock.patch.object(
                    cc, "_cmdline_of",
                    return_value="node /home/tardis/.npm/_npx/"
                                 "1e7f6d9597241db0/node_modules/.bin/dsh web"), \
                unittest.mock.patch.object(cc.time, "sleep"), \
                unittest.mock.patch.object(
                    cc, "_stop_dsh_instances",
                    side_effect=lambda pids, **k: None) as stop:
            self.assertIsNone(cc._ensure_port_free_for_dsh(3080))
        self.assertEqual(stop.call_args_list,
                         [unittest.mock.call([12059])])

    def test_ensure_port_refuses_foreign_listener(self):
        with unittest.mock.patch.object(
                cc, "_port_listener_pid",
                return_value=(777, "LISTEN")), \
                unittest.mock.patch.object(
                    cc, "_cmdline_of",
                    return_value="python -m http.server 3080"):
            reason = cc._ensure_port_free_for_dsh(3080)
        self.assertIn("proceso ajeno a DSH", reason)
        self.assertIn("777", reason)

    def test_launch_path_fails_closed_when_port_blocked(self):
        fake_client = unittest.mock.Mock()
        fake_client.authenticated = True
        fake_process = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ,
                                         {"TEST_PROV_KEY": "x"}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]), \
                unittest.mock.patch.object(
                    cc, "_ensure_port_free_for_dsh",
                    return_value="puerto 3080 ocupado por un proceso ajeno "
                                 "a DSH (PID 777)"), \
                unittest.mock.patch.object(
                    cc, "launch_dsh_web",
                    side_effect=AssertionError("must not launch")):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client(launch=True)
        self.assertIsNone(client)
        self.assertIn("puerto 3080 ocupado", origin)

    def test_existing_session_without_key_warns_and_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict(os.environ, {"DSH_HOME": tmp}), \
                unittest.mock.patch.dict(os.environ, {"TEST_PROV_KEY": ""}), \
                unittest.mock.patch.object(cc, "_find_dsh_pids",
                                           return_value=[]), \
                unittest.mock.patch.object(cc.DshLocalClient,
                                           "exchange_token",
                                           lambda self: None):
            _write_dsh_home(tmp)
            client, origin = cc.acquire_dsh_client()
        self.assertIsNotNone(client)
        self.assertIn("aviso:", origin)
        self.assertIn("ningún proveedor utilizable", origin)



class ValidatorTests(Base):
    def _make_contract_package(self, reuse_reference="systematic-debugging"):
        """Package with one contract artifact reusing a base skill."""
        contract = {
            "schema_version": 1,
            "name": "project-debugger",
            "motive": "Recurring debugging procedure",
            "domain": ["python-backend"],
            "reuse_source": "base-library",
            "reuse_reference": reuse_reference,
            "inputs": ["failure report"],
            "outputs": ["diagnosis"],
            "required_capabilities": ["product_read"],
            "forbidden_capabilities": ["product_write"],
            "files": [{"path": "SKILL.md", "type": "entrypoint",
                       "max_bytes": 32768}],
            "behavior_test": "SC-001",
            "provenance": {"license": "proprietary"},
        }
        generated, manifest = self.make_package()
        contracts = generated / "contracts"
        contracts.mkdir()
        (contracts / "skill-contract.json").write_text(
            json.dumps(contract, indent=2) + "\n")
        manifest["artifacts"].append({
            "path": "contracts/skill-contract.json",
            "type": "contract",
            "sha256": cc._digest_bytes(
                (contracts / "skill-contract.json").read_bytes()),
        })
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n")
        return generated, manifest

    def test_contract_reuse_reference_resolves_against_library(self):
        generated, _ = self._make_contract_package()
        report = hv.validate_package(generated, run_dir=self.run_dir)
        self.assertTrue(report.passed)
        self.assertEqual(report.verdict, "READY_FOR_ACCEPTANCE")

    def test_unknown_reuse_reference_retained(self):
        generated, _ = self._make_contract_package(
            reuse_reference="nonexistent-base-skill")
        report = hv.validate_package(generated, run_dir=self.run_dir)
        self.assertFalse(report.passed)
        self.assertEqual(report.verdict, "RETAINED")
        self.assertFalse(report.layers["contracts"]["passed"])
        self.assertIn("no existe en la biblioteca",
                      " ".join(report.layers["contracts"]["details"]))

    def test_contract_missing_reuse_reference_retained(self):
        generated, _ = self._make_contract_package(reuse_reference=None)
        contract = json.loads(
            (generated / "contracts" / "skill-contract.json").read_text())
        del contract["reuse_reference"]
        (generated / "contracts" / "skill-contract.json").write_text(
            json.dumps(contract, indent=2) + "\n")
        manifest = json.loads(
            (generated / "generation-manifest.json").read_text())
        for art in manifest["artifacts"]:
            if art["path"] == "contracts/skill-contract.json":
                art["sha256"] = cc._digest_bytes(
                    (generated / "contracts" / "skill-contract.json").read_bytes())
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n")
        report = hv.validate_package(generated, run_dir=self.run_dir)
        self.assertFalse(report.passed)
        self.assertIn("reuse_reference required",
                      " ".join(report.layers["contracts"]["details"]))

    def test_valid_package_ready(self):
        generated, _ = self.make_package()
        report = hv.validate_package(generated)
        self.assertTrue(report.passed)
        self.assertEqual(report.verdict, "READY_FOR_ACCEPTANCE")
        self.assertEqual(len(report.layers), 10)

    def test_bad_status_retained(self):
        generated, _ = self.make_package(status="ACTIVE")
        report = hv.validate_package(generated)
        self.assertFalse(report.passed)
        self.assertEqual(report.verdict, "RETAINED")
        self.assertFalse(report.layers["schema"]["passed"])

    def test_hash_mismatch_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["sha256"] = "0" * 64
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["manifest"]["passed"])

    def test_unsafe_path_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"][0]["path"] = "../escape"
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.passed)

    def test_capability_overlap_retained(self):
        generated, manifest = self.make_package(
            extra={"required_capabilities": ["network"],
                   "forbidden_capabilities": ["network"]}
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["capabilities"]["passed"])

    def test_portability_violation_retained(self):
        generated, manifest = self.make_package()
        skill = generated / "skills/project-auditor/SKILL.md"
        skill.write_text("import subprocess\nsubprocess.run(['x'])\n")
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["portability"]["passed"])

    def test_budget_violation_retained(self):
        generated, manifest = self.make_package()
        manifest["context_policy"]["skill_entrypoint_max_bytes"] = 1
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["context_budget"]["passed"])

    def test_host_only_artifact_retained(self):
        generated, manifest = self.make_package()
        manifest["artifacts"].append({
            "path": "host-verdict.json", "type": "report",
            "sha256": "a" * 64,
        })
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["lifecycle"]["passed"])

    def test_mit_requires_notice(self):
        generated, manifest = self.make_package(
            extra={"license_provenance": [{
                "file": "skills/project-auditor/SKILL.md",
                "source": "external", "license": "MIT",
            }]}
        )
        (generated / "generation-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
        report = hv.validate_package(generated)
        self.assertFalse(report.layers["license"]["passed"])

    def test_write_reports(self):
        generated, _ = self.make_package()
        report = hv.validate_package(generated)
        result = hv.write_reports(report, self.run_dir)
        self.assertTrue((self.run_dir / "validation" / "summary.json").is_file())
        self.assertEqual(result["verdict"], "READY_FOR_ACCEPTANCE")


if __name__ == "__main__":
    unittest.main()
