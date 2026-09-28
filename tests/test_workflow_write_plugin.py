"""Regression for the workflow-write DSH plugin (M7).

Mechanical, no models: a disposable preset mounts workflow_write and the same
relative anti-escalation row used by generated bundles, a real session is created,
and tools are driven through ctx.tools.execute. Asserts ordinary Bash works while
workspace-write and danger-full-access arguments are rejected before approval,
plus the M7 workflow_write compatibility path and filesystem denial.

DSH_MODULE_ROOT=/absolute/node_modules python3 -B -m unittest discover -s tests
"""
import json
from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import launch
from transaction import Transaction

FRAMEWORK = Path(__file__).resolve().parents[1]
PLUGIN = FRAMEWORK / 'scripts/dsh-plugins/workflow-write.mjs'

PRESET_YML = """name: workflow-write fixture
description: Regression fixture only; grants nothing outside this test.
order: 9
"""

ROW = """- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    prefix: Improvement runtime regression.
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
  config:
    includeDefaultRoots: false
    customSkillDirs:
      - /inputs/presets/skills
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: anti-escalation
  name: '/inputs/presets/anti-escalation.mjs'
"""

CHECK = r'''
import crypto from 'node:crypto';
import fs from 'node:fs';
import yaml from '/inputs/node_modules/yaml/dist/index.js';
import {runProfile} from '/inputs/node_modules/@deepseek-ai/dsh/lib/profile-boot.js';
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
  const callTool = (name, args) => boot.ctx.tools.execute({callId: 'probe-' + (seq++), name,
    arguments: args, agent, signal: AbortSignal.timeout(20000)});
  const call = args => callTool('workflow_write', args);
  const text = r => String(r.error?.message || (r.content || []).map(p => p.text).join(' ') || '').slice(0, 220);
  const preset = await rpc('agentPresets/read', {agentPreset: 'write-fixture'});
  const content = String(preset.value?.content || '');
  const expectedRows = ['persona', 'tool-bash', 'tool-fs', 'tool-fs-search',
    'skill-filesystem', 'tool-skill', 'anti-escalation'];
  report.composition = {guard: content.includes('/inputs/presets/anti-escalation.mjs'),
    workflowOutsidePreset: !content.includes('- id: workflow-write'),
    exactRows: expectedRows.every(id => content.includes(`- id: ${id}`)) &&
      (content.match(/^\s*- id: /gm) || []).length === expectedRows.length};

  const r1 = await call({file_path: '/state/ws/probe1.txt', content: 'ordinary'});
  report.ordinary = {isError: r1.isError, err: text(r1), written: fs.existsSync('/state/ws/probe1.txt')};

  const r2 = await call({file_path: '/state/ws/probe2.txt', content: 'same-mode',
    sandbox_permissions: 'workspace-write', justification: 'same mode'});
  report.sameMode = {isError: r2.isError, err: text(r2), written: fs.existsSync('/state/ws/probe2.txt')};

  const r3 = await callTool('bash', {command: 'printf ordinary', description: 'ordinary'});
  report.bashOrdinary = {isError: r3.isError, err: text(r3)};
  for (const mode of ['workspace-write', 'danger-full-access']) {
    const result = await callTool('bash', {command: 'printf forbidden', description: 'forbidden',
      sandbox_permissions: mode, justification: 'schema retry'});
    report['bash_' + mode] = {isError: result.isError, err: text(result)};
  }
  const r4 = await call({file_path: '/inputs/node_modules/evil.txt', content: 'no'});
  report.outside = {isError: r4.isError, err: text(r4)};

  report.ok = report.composition.guard && report.composition.workflowOutsidePreset &&
    report.composition.exactRows &&
    !r1.isError && report.ordinary.written && !r2.isError && report.sameMode.written &&
    !r3.isError && report['bash_workspace-write'].isError && report['bash_danger-full-access'].isError &&
    /RETAINED with no retry/.test(report['bash_workspace-write'].err) &&
    /RETAINED with no retry/.test(report['bash_danger-full-access'].err) && r4.isError;
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
        source = base / 'agent.cordis.yml'
        source.write_text(ROW.replace(
            "'/inputs/presets/anti-escalation.mjs'", "'./anti-escalation.mjs'"))
        shutil.copy2(FRAMEWORK / 'scripts/dsh-plugins/anti-escalation.mjs',
                     presets / 'anti-escalation.mjs')
        skill = presets / 'skills' / 'write-fixture'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text(
            '---\nname: write-fixture\ndescription: Runtime fixture\n---\nFixture.\n')
        check = root / 'check'
        check.mkdir()
        (root / 'runs').mkdir(mode=0o700)
        (check / 'probe-write.mjs').write_text(CHECK)
        published = Transaction._composition_with_skill_root(
            source, presets / 'skills')
        guard = str((presets / 'anti-escalation.mjs').resolve())
        self.assertIn(f'  name: "{guard}"', published)
        # host_launcher exposes this external bundle at /inputs/presets.
        mounted = [line.replace(guard, '/inputs/presets/anti-escalation.mjs')
                   for line in published]
        plugins = ''.join('          ' + line + '\n' for line in mounted)
        (check / 'patch.yml').write_text(
            '- insert:\n'
            "    - id: workflow-write\n      name: '/inputs/plugins/workflow-write.mjs'\n"
            "    - id: preset-write-fixture\n      name: '@deepseek-ai/dsh-agent-preset'\n"
            '      config:\n        id: write-fixture\n        name: workflow-write fixture\n'
            '        plugins:\n' + plugins)
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
        self.assertFalse(report['sameMode']['isError'], 'M7: workflow_write same-mode remains compatible')
        self.assertFalse(report['bashOrdinary']['isError'])
        self.assertTrue(report['bash_workspace-write']['isError'])
        self.assertTrue(report['bash_danger-full-access']['isError'])
        self.assertTrue(report['composition']['guard'])
        self.assertTrue(report['composition']['workflowOutsidePreset'])
        self.assertTrue(report['composition']['exactRows'])
        self.assertTrue(report['outside']['isError'], 'outside the writable area must be denied')


if __name__ == '__main__':
    unittest.main()
