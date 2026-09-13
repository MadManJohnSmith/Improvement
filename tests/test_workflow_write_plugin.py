"""Regression for the workflow-write DSH plugin (M7).

Mechanical, no models: a disposable preset mounts the plugin by absolute path
(the loader resolves absolute row names), a real session is created, and the
tool is driven through ctx.tools.execute. Asserts the M7 fix (a same-mode
sandbox_permissions writes instead of failing "not strictly wider"), the
ordinary path, and the fail-closed denial outside the writable area.

DSH_MODULE_ROOT=/absolute/node_modules python3 -B -m unittest discover -s tests
"""
import json
from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import launch

FRAMEWORK = Path(__file__).resolve().parents[1]
PLUGIN = FRAMEWORK / 'scripts/dsh-plugins/workflow-write.mjs'

PRESET_YML = """name: workflow-write fixture
description: Regression fixture only; grants nothing outside this test.
order: 9
"""

ROW = """- id: workflow-write
  name: '/inputs/plugins/workflow-write.mjs'
"""

CHECK = r'''
import crypto from 'node:crypto';
import fs from 'node:fs';
import yaml from '/inputs/node_modules/yaml/dist/index.js';
import {runProfile} from '/inputs/node_modules/@deepseek-ai/dsh/lib/profile-boot-BP_C0vpU.js';
import {loadLayeredEnv} from '/inputs/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js';
process.stdout.write = () => true;
const report = {};
let boot;
try {
  const DSH_HOME = '/state/dsh-home';
  fs.mkdirSync(`${DSH_HOME}/sessions`, {recursive: true});
  fs.writeFileSync(`${DSH_HOME}/settings.yaml`, yaml.stringify({
    'llm-pi-ai': {providers: {'fixture-provider': {api: 'openai-completions',
      baseURL: 'http://127.0.0.1:9/v1', apiKeyEnv: 'FIXTURE_UNUSED', models: [{id: 'fixture-model'}]}}},
    'agent-default-model': {provider: 'fixture-provider', model: 'fixture-model'},
  }));
  boot = await runProfile({profile: 'web', patchFiles: ['/inputs/check/patch.yml'],
    args: ['--host', '127.0.0.1', '--port', '3491', '--no-open'], environment: loadLayeredEnv('dsh')});
  if (boot.ctx.fiber.state !== 2) throw new Error('profile state ' + boot.ctx.fiber.state);

  function decodeB64u(v) { const p = '='.repeat((4 - (v.length % 4)) % 4); return Buffer.from(v.replaceAll('-', '+').replaceAll('_', '/') + p, 'base64'); }
  function encodeB64u(b) { return Buffer.from(b).toString('base64').replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, ''); }
  const creds = yaml.parse(fs.readFileSync(`${DSH_HOME}/.credentials.yaml`, 'utf8'));
  const secret = decodeB64u(creds.records['client-connection/browser-session'].payload.secret);
  const authority = '127.0.0.1:3491';
  const cookieName = 'dsh-auth-' + encodeB64u(crypto.createHash('sha256').update(authority).digest());
  const now = Date.now();
  const body = encodeB64u(Buffer.from(JSON.stringify({version: 1, authority, issuedAt: now, expiresAt: now + 3600000}), 'utf8'));
  const cookie = `${cookieName}=v1.${body}.${encodeB64u(crypto.createHmac('sha256', secret).update(body).digest())}`;
  let seq = 0;
  const rpc = async (method, args) => {
    const res = await fetch(`http://${authority}/api/${method}`, {method: 'POST',
      headers: {'Content-Type': 'application/json', Cookie: cookie, Host: authority},
      body: JSON.stringify({type: 'client-request', rpcId: `r${seq++}`, method, payload: {args}})});
    const json = await res.json();
    return {ok: json.result?.ok === true, value: json.result?.value, error: json.result?.error};
  };

  fs.mkdirSync('/state/ws', {recursive: true});
  const created = await rpc('session/create', {request: {cwd: '/state/ws', agentPreset: 'write-fixture'}});
  if (!created.ok) throw new Error('session: ' + JSON.stringify(created.error));
  const agent = boot.ctx.agents.get(created.value.sessionId);
  const call = args => boot.ctx.tools.execute({callId: 'probe-' + (seq++), name: 'workflow_write',
    arguments: args, agent, signal: AbortSignal.timeout(20000)});
  const text = r => String(r.error?.message || (r.content || []).map(p => p.text).join(' ') || '').slice(0, 220);

  const r1 = await call({file_path: '/state/ws/probe1.txt', content: 'ordinary'});
  report.ordinary = {isError: r1.isError, err: text(r1), written: fs.existsSync('/state/ws/probe1.txt')};

  const r2 = await call({file_path: '/state/ws/probe2.txt', content: 'same-mode',
    sandbox_permissions: 'workspace-write', justification: 'same mode'});
  report.sameMode = {isError: r2.isError, err: text(r2), written: fs.existsSync('/state/ws/probe2.txt')};

  const r4 = await call({file_path: '/inputs/node_modules/evil.txt', content: 'no'});
  report.outside = {isError: r4.isError, err: text(r4)};

  report.ok = !r1.isError && report.ordinary.written && !r2.isError && report.sameMode.written && r4.isError;
} catch (error) {
  report.fatal = String(error && error.stack || error).slice(0, 1200);
  report.ok = false;
}
fs.writeFileSync('/state/probe.json', JSON.stringify(report, null, 1));
if (boot) await boot.shutdown.shutdown(report.ok ? 0 : 1); else process.exit(1);
'''


class WorkflowWritePluginTest(unittest.TestCase):
    def test_same_mode_escalation_writes_and_outside_denied(self):
        runtime = __import__('os').environ.get('DSH_MODULE_ROOT')
        if not runtime:
            self.skipTest('Set DSH_MODULE_ROOT to installed runtime; no installation/fallback')
        root = Path(__import__('tempfile').mkdtemp(prefix='workflow-write-', dir='/tmp'))
        presets = root / 'presets'
        base = presets / 'write-fixture'
        base.mkdir(parents=True)
        (base / 'preset.yml').write_text(PRESET_YML)
        (base / 'agent.cordis.yml').write_text(ROW)
        check = root / 'check'
        check.mkdir()
        (root / 'runs').mkdir(mode=0o700)
        (check / 'probe-write.mjs').write_text(CHECK)
        (check / 'patch.yml').write_text(
            '- id: agent-presets\n  config:\n    default: standard\n    roots:\n'
            '      - path: /inputs/presets\n        trust: system\n')
        state, code = launch(reads={'node_modules': Path(runtime), 'presets': presets,
                                    'check': check,
                                    'plugins': FRAMEWORK / 'scripts/dsh-plugins'},
                             state_parent=root / 'runs', cwd=check,
                             argv=['/usr/bin/node', '/inputs/check/probe-write.mjs'], timeout=240)
        self.assertEqual(code, 0, (state / 'probe.json').read_text() if (state / 'probe.json').exists()
                         else (state / 'stderr.log').read_text()[-3000:])
        report = json.loads((state / 'probe.json').read_text())
        self.assertTrue(report['ok'], report)
        self.assertFalse(report['ordinary']['isError'])
        self.assertFalse(report['sameMode']['isError'], 'M7: same-mode must write, not fail closed')
        self.assertTrue(report['outside']['isError'], 'outside the writable area must be denied')


if __name__ == '__main__':
    unittest.main()
