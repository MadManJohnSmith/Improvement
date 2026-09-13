"""Regression for the external workflow presets' model mapping (Phase A).

Fixture-only: a synthetic preset declares `modelSelectionSettings: true` and the
isolated Host's disposable settings carry the authorized exact routes. Asserts
the effective mapping (session route + durable allowedModels policy) and the
fail-closed rejection of routes outside `allowedModels`. No credentials, no
gateway, no model calls: denial happens at policy preflight and the boot never
requests inference.

DSH_MODULE_ROOT=/absolute/node_modules python3 -B -m unittest discover -s tests
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import launch


PRESET_YML = """name: Mapping fixture
description: Regression fixture only; grants nothing outside this test.
order: 9
"""

PRESET_COMPOSITION = """- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    suffix: Your working directory is {{cwd}}.
    prefix: >-
      You are a coding agent powered by the {{model}} model.

- id: tool-fs
  name: '@deepseek-ai/dsh-tool-fs'

- id: delegation
  name: cordis:group
  group: true
  isolate:
    workflowEngine: true
  config:
    - id: tool-subagent-control
      name: '@deepseek-ai/dsh-tool-subagent-control'

    - id: tool-subagent-list-agents
      name: '@deepseek-ai/dsh-tool-subagent-control/list-agents'

    - id: tool-subagent
      name: '@deepseek-ai/dsh-tool-subagent'
      config:
        provider: spawn
        toolName: subagent
        modelSelectionSettings: true
        backgroundMode: continuable

    - id: tool-subagent-fork
      name: '@deepseek-ai/dsh-tool-subagent'
      config:
        provider: fork
        toolName: subagent_fork
        backgroundMode: continuable

    - id: workflow-worker-thread
      name: '@deepseek-ai/dsh-workflow-worker-thread'
      config:
        provider: spawn

    - id: tool-workflow
      name: '@deepseek-ai/dsh-tool-workflow'
"""

# A preset that carries its own model-selection-settings service row is refused:
# the Host web composition already owns that settings namespace, and a second
# registration throws, so session creation fails loud instead of falling back.
PRESET_COMPOSITION_OWN_SELECTION = PRESET_COMPOSITION + """
- id: selection-settings
  name: '@deepseek-ai/dsh-tool-subagent/model-selection-settings'
  config:
    enabled: true
    allowedModels:
      - provider: fixture-provider
        model: fixture-model
"""

CHECK = r'''
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import yaml from '/inputs/node_modules/yaml/dist/index.js';
import {runProfile} from '/inputs/node_modules/@deepseek-ai/dsh/lib/profile-boot-BP_C0vpU.js';
import {loadLayeredEnv} from '/inputs/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js';
process.stdout.write = () => true;
process.stderr.write = () => true;

// Non-secret fixture routes: one allowed route, two explicit denial probes.
const P = JSON.parse(fs.readFileSync('/inputs/check/params.json', 'utf8'));
const DSH_HOME = '/state/dsh-home';
fs.mkdirSync(DSH_HOME, {recursive: true});
fs.writeFileSync(`${DSH_HOME}/settings.yaml`, yaml.stringify({
  'llm-pi-ai': {providers: {
    'fixture-provider': {api: 'openai-completions', baseURL: 'http://127.0.0.1:9/v1',
      apiKeyEnv: 'FIXTURE_UNUSED', models: [{id: 'fixture-model'}, {id: 'fixture-unlisted'}]},
  }},
  'agent-default-model': {provider: 'fixture-provider', model: 'fixture-model'},
  'subagent-model-selection': {enabled: true, allowedModels: P.allowedModels},
}));

const report = {};
let boot;
try {
  boot = await runProfile({profile: 'web', patchFiles: ['/inputs/patch/mapping-patch.yml'],
    args: ['--host', '127.0.0.1', '--port', '3480', '--no-open'],
    environment: loadLayeredEnv('dsh')});
  assert.equal(boot.ctx.fiber.state, 2);

  function decodeB64u(v) { const p = '='.repeat((4 - (v.length % 4)) % 4); return Buffer.from(v.replaceAll('-', '+').replaceAll('_', '/') + p, 'base64'); }
  function encodeB64u(b) { return Buffer.from(b).toString('base64').replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, ''); }
  const creds = yaml.parse(fs.readFileSync(`${DSH_HOME}/.credentials.yaml`, 'utf8'));
  const secret = decodeB64u(creds.records['client-connection/browser-session'].payload.secret);
  const authority = '127.0.0.1:3480';
  const cookieName = 'dsh-auth-' + encodeB64u(crypto.createHash('sha256').update(authority).digest());
  const now = Date.now();
  const body = encodeB64u(Buffer.from(JSON.stringify({version: 1, authority, issuedAt: now, expiresAt: now + 3600000}), 'utf8'));
  const cookie = `${cookieName}=v1.${body}.${encodeB64u(crypto.createHmac('sha256', secret).update(body).digest())}`;
  let rpcSeq = 0;
  const rpc = async (method, args) => {
    const res = await fetch(`http://${authority}/api/${method}`, {method: 'POST',
      headers: {'Content-Type': 'application/json', 'Cookie': cookie, 'Host': authority},
      body: JSON.stringify({type: 'client-request', rpcId: `rpc-${rpcSeq++}`, method, payload: {args}})});
    const json = await res.json();
    return {ok: json.result?.ok === true, value: json.result?.value, error: json.result?.error};
  };

  // Effective mapping: the session route is the fixture default and the durable
  // policy projection is exactly the fixture allowedModels list.
  const created = await rpc('session/create', {request: {cwd: '/inputs/workspace', agentPreset: P.presetId}});
  assert.ok(created.ok, JSON.stringify(created.error));
  const sid = created.value.sessionId;
  const agent = boot.ctx.agents.get(sid);
  assert.ok(agent);
  assert.equal(agent.options.provider, 'fixture-provider');
  assert.equal(agent.options.model, 'fixture-model');
  const policy = boot.ctx.sessionProjections.stateOf(agent.session, 'subagentModelSelectionPolicy');
  assert.deepEqual(policy, P.allowedModels);

  const text = res => {
    const out = [];
    const walk = (v, d) => { if (d > 5 || v == null || out.length > 60) return; if (typeof v === 'string') { out.push(v); return; } if (Array.isArray(v)) { for (const x of v) walk(x, d + 1); return; } if (typeof v === 'object') { for (const x of Object.values(v)) walk(x, d + 1); } };
    walk(res, 0); return out.join('\n');
  };

  // Fail-closed: every route outside allowedModels is rejected before child
  // creation; no inference channel is mounted in this launch at all.
  for (const [label, route] of Object.entries(P.deniedRoutes)) {
    const res = await boot.ctx.tools.execute({callId: `regression-${label}`, name: 'subagent',
      arguments: {description: label, prompt: 'ignored', provider: route.provider,
        model: route.model, run_in_background: false},
      agent, signal: AbortSignal.timeout(20000)});
    assert.equal(res.isError, true, `${label}: expected denial`);
    assert.match(text(res), /not allowed for this Session/, `${label}: ${text(res).slice(0, 200)}`);
    report[label] = text(res).match(/Error: [^\n]*/)[0].slice(0, 160);
  }

  // A preset claiming its own selection settings fails the mount loud.
  const own = await rpc('session/create', {request: {cwd: '/inputs/workspace', agentPreset: P.ownSelectionPresetId}});
  assert.equal(own.ok, false, 'own-selection preset must fail closed');
  report.ownSelectionPresetRefused = JSON.stringify(own.error).slice(0, 200);

  report.ok = true;
} catch (error) {
  report.fatal = String(error && error.message || error).slice(0, 400);
}
fs.writeFileSync('/state/checked.json', JSON.stringify(report, null, 1));
if (boot) await boot.shutdown.shutdown(report.ok ? 0 : 1); else process.exit(1);
'''


class PresetMappingTest(unittest.TestCase):
    def test_fixture_mapping_and_fail_closed(self):
        runtime = os.environ.get('DSH_MODULE_ROOT')
        if not runtime:
            self.skipTest('Set DSH_MODULE_ROOT to installed runtime; no installation/fallback')
        root = Path(tempfile.mkdtemp(prefix='preset-mapping-', dir='/tmp'))
        print(f'Preset mapping evidence: {root}', flush=True)
        presets = root / 'presets'
        allowed = [{'provider': 'fixture-provider', 'model': 'fixture-model'},
                   {'provider': 'other-fixture', 'model': 'other-model'}]
        for preset_id, composition in (('mapping-fixture', PRESET_COMPOSITION),
                                       ('own-selection-fixture', PRESET_COMPOSITION_OWN_SELECTION)):
            base = presets / preset_id
            base.mkdir(parents=True)
            (base / 'preset.yml').write_text(PRESET_YML)
            (base / 'agent.cordis.yml').write_text(composition)
        (root / 'patch').mkdir()
        (root / 'patch' / 'mapping-patch.yml').write_text(
            '- id: agent-presets\n  config:\n    default: standard\n    roots:\n'
            '      - path: /inputs/presets\n        trust: system\n')
        (root / 'workspace').mkdir()
        state_parent = root / 'runs'
        state_parent.mkdir(mode=0o700)
        check = root / 'check'
        check.mkdir()
        (check / 'check.mjs').write_text(CHECK)
        (check / 'params.json').write_text(json.dumps({
            'presetId': 'mapping-fixture', 'ownSelectionPresetId': 'own-selection-fixture',
            'allowedModels': allowed,
            'deniedRoutes': {
                'unlistedProvider': {'provider': 'never-registered', 'model': 'any-model'},
                'unlistedModel': {'provider': 'fixture-provider', 'model': 'fixture-unlisted'},
            }}))
        state, code = launch(reads={'node_modules': runtime, 'presets': presets,
                                    'workspace': root / 'workspace', 'check': check,
                                    'patch': root / 'patch'},
                             state_parent=state_parent, cwd=root / 'workspace',
                             argv=['/usr/bin/node', '/inputs/check/check.mjs'], timeout=240)
        self.assertEqual(code, 0, (state / 'stderr.log').read_text()[-3000:])
        report = (state / 'checked.json').read_text()
        print(report, flush=True)
        self.assertIn('"ok": true', report)
        self.assertIn('not allowed for this Session', report)


if __name__ == '__main__':
    unittest.main()
