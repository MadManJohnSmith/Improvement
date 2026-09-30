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
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import launch
import stack
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
  // A managed Improvement session: the workspace is an immediate child of the
  // session cwd and the Host marked it with its capability plan, so state
  // writes are confined to <workspace>/mode-state and the product is not one.
  const managed = '/state/ws/Improvement-workspace';
  fs.mkdirSync(`${managed}/mode-state`, {recursive: true});
  fs.mkdirSync(`${managed}/.dsh-managed`, {recursive: true});
  fs.writeFileSync(`${managed}/.dsh-managed/capability-plan.json`,
    JSON.stringify({version: 1, workspace: managed, stacks: []}));
  fs.mkdirSync('/state/ws/Improvement/scripts', {recursive: true});
  fs.writeFileSync('/state/ws/Improvement/scripts/stack.py', 'CANONICAL = true\n');
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

  const r1 = await call({file_path: `${managed}/mode-state/probe1.txt`, content: 'ordinary'});
  report.ordinary = {isError: r1.isError, err: text(r1), written: fs.existsSync(`${managed}/mode-state/probe1.txt`)};

  const r2 = await call({file_path: `${managed}/mode-state/probe2.txt`, content: 'same-mode',
    sandbox_permissions: 'workspace-write', justification: 'same mode'});
  report.sameMode = {isError: r2.isError, err: text(r2), written: fs.existsSync(`${managed}/mode-state/probe2.txt`)};

  const r3 = await callTool('bash', {command: 'printf ordinary', description: 'ordinary'});
  report.bashOrdinary = {isError: r3.isError, err: text(r3)};
  for (const mode of ['workspace-write', 'danger-full-access']) {
    const result = await callTool('bash', {command: 'printf forbidden', description: 'forbidden',
      sandbox_permissions: mode, justification: 'schema retry'});
    report['bash_' + mode] = {isError: result.isError, err: text(result)};
  }
  const r4 = await call({file_path: '/inputs/node_modules/evil.txt', content: 'no'});
  report.outside = {isError: r4.isError, err: text(r4)};

  const r5 = await call({file_path: '/state/ws/Improvement/scripts/stack.py', content: 'mutado'});
  report.productWrite = {isError: r5.isError, err: text(r5),
    unchanged: fs.readFileSync('/state/ws/Improvement/scripts/stack.py', 'utf8') === 'CANONICAL = true\n'};

  report.ok = report.composition.guard && report.composition.workflowOutsidePreset &&
    report.composition.exactRows &&
    !r1.isError && report.ordinary.written && !r2.isError && report.sameMode.written &&
    !r3.isError && report['bash_workspace-write'].isError && report['bash_danger-full-access'].isError &&
    /RETAINED with no retry/.test(report['bash_workspace-write'].err) &&
    /RETAINED with no retry/.test(report['bash_danger-full-access'].err) && r4.isError &&
    report.productWrite.isError && report.productWrite.unchanged;
} catch (error) {
  report.fatal = String(error && error.stack || error).slice(0, 1200);
  report.ok = false;
}
fs.writeFileSync('/state/probe.json', JSON.stringify(report, null, 1));
if (boot) await boot.shutdown.shutdown(report.ok ? 0 : 1); else process.exit(1);
'''

# Drives the real plugin module against a managed Improvement session, without
# the DSH runtime: a fake ctx supplies only the fs/policy services the tool
# already calls, so the confinement decision under test is the plugin's own.
CONFINEMENT_DRIVER = r'''
import fs from 'node:fs';
import path from 'node:path';
import {apply} from 'PLUGIN_PATH';

const canonical = (raw) => {
  const absolute = path.resolve(raw);
  let probe = absolute;
  while (!fs.existsSync(probe)) {
    const parent = path.dirname(probe);
    if (parent === probe) return absolute;
    probe = parent;
  }
  return path.join(fs.realpathSync(probe), path.relative(probe, absolute));
};

function makeCtx(root) {
  let registered;
  const ctx = {
    get: (name) => (name === 'sandboxPolicy'
      ? {resolve: () => ({mode: 'workspace-write', workspaceRoot: root})} : undefined),
    on: () => {},
    emit: () => {},
    tools: {register: (definition) => { registered = definition; }, guard: () => {}, get: () => undefined},
    waterfall: async (...args) => {
      const next = args[args.length - 1];
      return typeof next === 'function' ? next() : undefined;
    },
    fs: {
      resolve: async (raw, opts = {}) => {
        if (typeof raw !== 'string' || raw.trim() === '') throw new Error('file_path must be a non-empty string');
        const absolute = canonical(path.isAbsolute(raw) ? raw : path.join(opts.cwd ?? root, raw));
        return {targetKey: absolute, displayPath: absolute};
      },
      processPath: (target) => target.targetKey,
      stat: async (target) => {
        try {
          const info = fs.lstatSync(target.targetKey);
          return {version: String(info.mtimeMs), type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
        } catch { return undefined; }
      },
      listDir: async (target) => fs.readdirSync(target.targetKey, {withFileTypes: true}).map((entry) => ({
        name: entry.name,
        type: entry.isDirectory() ? 'directory' : entry.isFile() ? 'file' : 'other',
        target: {targetKey: path.join(target.targetKey, entry.name), displayPath: path.join(target.targetKey, entry.name)},
      })),
      readText: async (target) => fs.readFileSync(target.targetKey, 'utf8'),
      writeText: async (target, content) => {
        const before = fs.existsSync(target.targetKey) ? fs.readFileSync(target.targetKey, 'utf8') : null;
        fs.mkdirSync(path.dirname(target.targetKey), {recursive: true});
        fs.writeFileSync(target.targetKey, content, 'utf8');
        return {version: 'v1', operation: before === null ? 'create' : 'update', before, after: content};
      },
    },
  };
  apply(ctx, {});
  return registered;
}

async function attempt(root, filePath, content) {
  const definition = makeCtx(root);
  const exec = {agent: {session: {header: {cwd: root}}}, callId: 'probe'};
  try {
    return {ok: true, value: await definition.execute({file_path: filePath, content}, exec)};
  } catch (error) {
    return {ok: false, error: String(error?.message || error)};
  }
}

const report = {};
const product = path.join(process.argv[2], 'Improvement', 'scripts', 'stack.py');
const before = fs.readFileSync(product, 'utf8');
report.stateWrite = await attempt(process.argv[2], 'Improvement-workspace/mode-state/work-items.json', '{"schema_version":1,"candidate":null,"items":[]}');
report.productWrite = await attempt(process.argv[2], 'Improvement/scripts/stack.py', 'mutated by a state write');
report.productUnchanged = fs.readFileSync(product, 'utf8') === before;
report.reviewerWrite = await attempt(process.argv[3], 'result.json', '{"verdict":"PASS"}');
process.stdout.write(JSON.stringify(report));
'''

# Drives the real plugin against a managed session and the managed
# verification-results file. The Python side owns the plan bytes, so the digest is
# produced by the production canonicalization (stack.py) and not by a re-implementation
# living in the fixture. Each case swaps only one of the three G7 inputs — the
# recorded command, the stack availability, or the plan digest — and the report
# says whether the write actually reached the disk.
PLAN_BINDING_DRIVER = r'''
import fs from 'node:fs';
import path from 'node:path';
import {apply} from 'PLUGIN_PATH';

const canonical = (raw) => {
  const absolute = path.resolve(raw);
  let probe = absolute;
  while (!fs.existsSync(probe)) {
    const parent = path.dirname(probe);
    if (parent === probe) return absolute;
    probe = parent;
  }
  return path.join(fs.realpathSync(probe), path.relative(probe, absolute));
};

function makeCtx(root) {
  let registered;
  const ctx = {
    get: (name) => (name === 'sandboxPolicy'
      ? {resolve: () => ({mode: 'workspace-write', workspaceRoot: root})} : undefined),
    on: () => {},
    emit: () => {},
    tools: {register: (definition) => { registered = definition; }, guard: () => {}, get: () => undefined},
    waterfall: async (...args) => {
      const next = args[args.length - 1];
      return typeof next === 'function' ? next() : undefined;
    },
    fs: {
      resolve: async (raw, opts = {}) => {
        if (typeof raw !== 'string' || raw.trim() === '') throw new Error('file_path must be a non-empty string');
        const absolute = canonical(path.isAbsolute(raw) ? raw : path.join(opts.cwd ?? root, raw));
        return {targetKey: absolute, displayPath: absolute};
      },
      processPath: (target) => target.targetKey,
      stat: async (target) => {
        try {
          const info = fs.lstatSync(target.targetKey);
          return {version: String(info.mtimeMs), type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
        } catch { return undefined; }
      },
      listDir: async (target) => fs.readdirSync(target.targetKey, {withFileTypes: true}).map((entry) => ({
        name: entry.name,
        type: entry.isDirectory() ? 'directory' : entry.isFile() ? 'file' : 'other',
        target: {targetKey: path.join(target.targetKey, entry.name), displayPath: path.join(target.targetKey, entry.name)},
      })),
      readText: async (target) => fs.readFileSync(target.targetKey, 'utf8'),
      writeText: async (target, content) => {
        const before = fs.existsSync(target.targetKey) ? fs.readFileSync(target.targetKey, 'utf8') : null;
        fs.mkdirSync(path.dirname(target.targetKey), {recursive: true});
        fs.writeFileSync(target.targetKey, content, 'utf8');
        return {version: 'v1', operation: before === null ? 'create' : 'update', before, after: content};
      },
    },
  };
  apply(ctx, {});
  return registered;
}

async function attempt(root, filePath, content) {
  const definition = makeCtx(root);
  const exec = {agent: {session: {header: {cwd: root}}}, callId: 'probe'};
  try {
    return {ok: true, value: await definition.execute({file_path: filePath, content}, exec)};
  } catch (error) {
    return {ok: false, error: String(error?.message || error)};
  }
}

const session = process.argv[2];
const cases = JSON.parse(fs.readFileSync(path.join(session, 'fixture.json'), 'utf8'));
const planPath = path.join(session, 'Improvement-workspace', '.dsh-managed', 'capability-plan.json');
const relative = 'Improvement-workspace/mode-state/verification-results.jsonl';
const targetPath = path.join(session, relative);
const report = {};
for (const [name, spec] of Object.entries(cases)) {
  fs.writeFileSync(planPath, spec.plan);
  fs.rmSync(targetPath, {force: true});
  const outcome = await attempt(session, relative, spec.content);
  report[name] = {ok: outcome.ok, error: outcome.error || '',
    written: fs.existsSync(targetPath),
    onDisk: fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null};
}
process.stdout.write(JSON.stringify(report));
'''


class WorkflowWritePluginTest(unittest.TestCase):
    def _signed_plan(self, workspace, stacks):
        """Plan bytes signed the way the Host signs them and read back by the Host.

        The digest expression is the one ``stack.plan`` uses; ``stack.load`` is the
        production reader, so a canonicalization that drifted by so much as a
        separator would raise here instead of silently making the case green.
        """
        value = {"version": 1, "product": str(workspace.parent / "Improvement"),
                 "workspace": str(workspace), "stacks": stacks}
        value["plan_sha256"] = stack._digest(json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        stack.write(value, workspace)
        stack.load(workspace)
        return (workspace / stack.PLAN_RELATIVE).read_text()

    def test_state_write_is_confined_to_the_managed_state_root(self):
        """SR-3 is only true if the tool itself refuses a product path.

        The mode contract confines state writes to ``<workspace>/mode-state``
        and the read-only audit boundary depends on it, but the tool resolved
        any path inside the writable area: one misdirected workflow_write
        mutated the canonical product and only Git noticed afterwards.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-state-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement' / 'scripts' / 'stack.py'
        product.parent.mkdir(parents=True)
        product.write_text('CANONICAL = True\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            json.dumps({'version': 1, 'workspace': str(workspace), 'stacks': []}))
        (workspace / 'mode-state').mkdir()
        # A session with no managed workspace is not a state-write session: the
        # acceptance reviewer writes its own result.json and must keep working.
        reviewer = root / 'reviewer'
        reviewer.mkdir()
        driver = root / 'driver.mjs'
        driver.write_text(CONFINEMENT_DRIVER.replace(
            'PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run(
            [node, driver.as_posix(), session.as_posix(), reviewer.as_posix()],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)
        self.assertTrue(report['stateWrite']['ok'], report['stateWrite'])
        self.assertFalse(report['productWrite']['ok'], report['productWrite'])
        self.assertTrue(report['productUnchanged'],
                        'a denied state write still mutated the canonical product')
        self.assertTrue(report['reviewerWrite']['ok'], report['reviewerWrite'])

    def test_managed_verification_write_binds_the_capability_plan_digest(self):
        """IMP-AUD-006: the plan is a signed input of the managed write, not a hint.

        The plan lives in the session's writable area, so a rewritten plan could
        otherwise declare a hand-written harness as the product entrypoint and
        turn a green suite into recorded evidence. The tool recomputes
        plan_sha256 with the production canonicalization and refuses the write
        before writeText when it does not match. The three G7 inputs are mutated
        one at a time, so each rejection is attributable to the mutation and not
        to a neighbour that happens to fail too.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-plan-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        (session / 'Improvement' / 'scripts').mkdir(parents=True)
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / 'mode-state').mkdir()

        ready = {"name": "python", "verification_ready": True,
                 "verify_command": ["python3", "-B", "-m", "unittest", "discover", "-s", "tests"],
                 "lint_command": None}
        unavailable = dict(ready, verification_ready=False)
        entrypoint = '["python3","-B","-m","unittest","discover","-s","tests"]'
        record = {"finding_id": "A-01", "candidate_head": "a" * 40,
                  "candidate_diff_digest": "b" * 64,
                  "command": entrypoint, "result": "PASS"}
        signed = self._signed_plan(workspace, [ready])
        signed_unavailable = self._signed_plan(workspace, [unavailable])
        body = json.loads(signed)
        cases = {
            "intact": {"plan": signed, "content": json.dumps(record) + "\n"},
            "command": {"plan": signed,
                        "content": json.dumps(dict(record, command='["echo","stub"]')) + "\n"},
            "availability": {"plan": signed_unavailable,
                             "content": json.dumps(record) + "\n"},
            "digest": {"plan": json.dumps(dict(body, plan_sha256="0" * 64)) + "\n",
                       "content": json.dumps(record) + "\n"},
            "unsigned": {"plan": json.dumps(
                {k: v for k, v in body.items() if k != "plan_sha256"}) + "\n",
                "content": json.dumps(record) + "\n"},
        }
        (session / 'fixture.json').write_text(json.dumps(cases))
        driver = root / 'plan-driver.mjs'
        driver.write_text(PLAN_BINDING_DRIVER.replace(
            'PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run(
            [node, driver.as_posix(), session.as_posix()],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        self.assertTrue(report["intact"]["ok"], report["intact"])
        self.assertTrue(report["intact"]["written"], report["intact"])
        self.assertEqual(report["intact"]["onDisk"], json.dumps(record) + "\n")
        for name, expected in (("command", "comando ajeno"),
                               ("availability", "debe ser BLOCKED"),
                               ("digest", "capability-plan alterado"),
                               ("unsigned", "capability-plan alterado")):
            with self.subTest(case=name):
                outcome = report[name]
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(expected, outcome["error"])
                self.assertFalse(
                    outcome["written"],
                    f'{name} reached writeText: {outcome["onDisk"]!r}')

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
        self.assertTrue(report['productWrite']['isError'],
                        'a state write outside <workspace>/mode-state must be denied')
        self.assertTrue(report['productWrite']['unchanged'],
                        'the denied product write still mutated the product')


if __name__ == '__main__':
    unittest.main()
