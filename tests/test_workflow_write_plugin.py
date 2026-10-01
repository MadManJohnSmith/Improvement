"""Regression for the workflow-write DSH plugin (M7).

Mechanical, no models: a disposable preset mounts workflow_write and the same
relative anti-escalation row used by generated bundles, a real session is created,
and tools are driven through ctx.tools.execute. Asserts ordinary Bash works while
workspace-write and danger-full-access arguments are rejected before approval,
plus the M7 workflow_write compatibility path and filesystem denial.

DSH_MODULE_ROOT=/absolute/node_modules python3 -B -m unittest discover -s tests
"""
import json
import os
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
// The profile-boot entrypoint is resolved from the installed runtime instead of
// being hardcoded: 0.1.5-alpha.1 ships content-hashed chunk names only
// (profile-boot-<hash>.js) while 0.2.x adds the stable lib/profile-boot.js, so a
// fixed path silently breaks the probe on whichever version it does not match.
const DSH_LIB = '/inputs/node_modules/@deepseek-ai/dsh/lib';
const profileBoot = ['profile-boot.js',
  ...fs.readdirSync(DSH_LIB).filter((n) => n.startsWith('profile-boot-'))
    .map((n) => `${DSH_LIB}/${n}`)]
  .map((n) => (n.startsWith('/') ? n : `${DSH_LIB}/${n}`))
  .find((n) => fs.existsSync(n));
if (profileBoot === undefined) throw new Error('dsh runtime has no profile-boot entrypoint');
const {runProfile} = await import(profileBoot);
const {loadLayeredEnv} = await import('/inputs/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js');
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

# Drives the real plugin against a managed session's handoffs.jsonl. The Python
# side owns the findings bytes, so each case mutates one of the three inputs the
# handoff claim rests on — a named finding that is not persisted, an OPEN finding
# left out of the audit handoff, and the record shape — and the report says
# whether the write actually reached the disk.
HANDOFF_DRIVER = r'''
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
const relative = 'Improvement-workspace/mode-state/handoffs.jsonl';
const targetPath = path.join(session, relative);
const findingsPath = path.join(session, 'Improvement-workspace', 'mode-state', 'findings.jsonl');
const report = {};
for (const [name, spec] of Object.entries(cases)) {
  fs.writeFileSync(findingsPath, spec.findings);
  fs.rmSync(targetPath, {force: true});
  const outcome = await attempt(session, relative, spec.content);
  report[name] = {ok: outcome.ok, error: outcome.error || '',
    written: fs.existsSync(targetPath),
    onDisk: fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null};
}
process.stdout.write(JSON.stringify(report));
'''


ANCHOR_DRIVER = r'''
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
          return {version: String(info.mtimeMs), size: info.size,
            type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
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
const relative = 'Improvement-workspace/mode-state/findings.jsonl';
const targetPath = path.join(session, relative);
const report = {};
for (const [name, spec] of Object.entries(cases)) {
  fs.rmSync(targetPath, {force: true});
  const outcome = await attempt(session, relative, spec);
  report[name] = {ok: outcome.ok, error: outcome.error || '',
    written: fs.existsSync(targetPath),
    onDisk: fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null,
    after: outcome.ok ? outcome.value?.after ?? null : null};
}
process.stdout.write(JSON.stringify(report));
'''


EVIDENCE_DRIVER = r'''
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
          return {version: String(info.mtimeMs), size: info.size,
            type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
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
const spec = JSON.parse(fs.readFileSync(path.join(session, 'fixture.json'), 'utf8'));
const report = {};
for (const [name, item] of Object.entries(spec.cases)) {
  const targetPath = path.join(session, item.path);
  fs.rmSync(targetPath, {force: true});
  const outcome = await attempt(session, item.path, item.content);
  report[name] = {ok: outcome.ok, error: outcome.error || '',
    written: fs.existsSync(targetPath)};
}
report.presentAfter = fs.existsSync(path.join(session, 'Improvement-workspace/evidence/kept.log'));
process.stdout.write(JSON.stringify(report));
'''


LEASE_DRIVER = r'''
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
          return {version: String(info.mtimeMs), size: info.size,
            type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
        } catch { return undefined; }
      },
      listDir: async (target) => fs.readdirSync(target.targetKey, {withFileTypes: true}).map((entry) => ({
        name: entry.name,
        type: entry.isDirectory() ? 'directory' : entry.isFile() ? 'file' : 'other',
        target: {targetKey: path.join(target.targetKey, entry.name), displayPath: path.join(target.targetKey, entry.name)},
      })),
      readText: async (target) => fs.readFileSync(target.targetKey, 'utf8'),
      writeText: async (target, content) => {
        fs.mkdirSync(path.dirname(target.targetKey), {recursive: true});
        fs.writeFileSync(target.targetKey, content, 'utf8');
        return {version: 'v1', operation: 'update', before: null, after: content};
      },
    },
  };
  apply(ctx, {});
  return registered;
}

async function attempt(root, filePath, content, sessionId) {
  const definition = makeCtx(root);
  const session = {id: sessionId, header: {cwd: root}};
  const exec = {agent: {session}, callId: 'probe'};
  try {
    return {ok: true, value: await definition.execute({file_path: filePath, content}, exec)};
  } catch (error) {
    return {ok: false, error: String(error?.message || error)};
  }
}

const session = process.argv[2];
const findings = 'Improvement-workspace/mode-state/findings.jsonl';
const artifact = 'Improvement-workspace/evidence/note.log';
const leasePath = path.join(session, 'Improvement-workspace/mode-state/.leases/findings.jsonl.json');
const finding = {finding_id: 'A-01', base_revision: 'a'.repeat(40), severity: 'HIGH',
                 summary: 'Missing validation', status: 'OPEN'};
const report = {};

const hold = (lease) => {
  fs.mkdirSync(path.dirname(leasePath), {recursive: true});
  fs.writeFileSync(leasePath, JSON.stringify(lease));
};

hold({target: 'findings.jsonl', session: 'other-session', acquired_at: Date.now() - 5000,
      expires_at: Date.now() + 25000, state: 'held'});
report.held_by_other = await attempt(session, findings, JSON.stringify(finding) + '\n', 'me');
report.heldError = fs.existsSync(leasePath) ? JSON.parse(fs.readFileSync(leasePath, 'utf8')).session : null;

hold({target: 'findings.jsonl', session: 'other-session', acquired_at: Date.now() - 60000,
      expires_at: Date.now() - 30000, state: 'held'});
report.expired = await attempt(session, findings, JSON.stringify(finding) + '\n', 'me');

hold({target: 'findings.jsonl', session: 'me', acquired_at: Date.now() - 5000,
      expires_at: Date.now() + 25000, state: 'held'});
report.held_by_self = await attempt(session, findings, JSON.stringify(finding) + '\n', 'me');
report.leaseAfterWrite = JSON.parse(fs.readFileSync(leasePath, 'utf8'));

fs.rmSync(path.join(session, artifact), {force: true});
report.artifact = await attempt(session, artifact, 'log\n', 'me');
report.artifactLease = fs.existsSync(
  path.join(session, 'Improvement-workspace/mode-state/.leases/note.log.json'));
report.anonymous = await attempt(session, 'Improvement-workspace/mode-state/work-items.json',
                                 '{"schema_version":1,"candidate":null,"items":[]}', null);
process.stdout.write(JSON.stringify(report));
'''


MEMORY_DRIVER = r'''
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
          return {version: String(info.mtimeMs), size: info.size,
            type: info.isDirectory() ? 'directory' : info.isFile() ? 'file' : 'other'};
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
const spec = JSON.parse(fs.readFileSync(path.join(session, 'fixture.json'), 'utf8'));
const relative = 'Improvement-workspace/mode-state/findings.jsonl';
const targetPath = path.join(session, relative);
const indexPath = path.join(session, 'Improvement-workspace/mode-state/episodes-index.json');
const report = {};
for (const [name, item] of Object.entries(spec)) {
  fs.rmSync(targetPath, {force: true});
  fs.rmSync(indexPath, {force: true});
  if (item.index !== null) fs.writeFileSync(indexPath, item.index, 'utf8');
  const outcome = await attempt(session, relative, item.content);
  report[name] = {ok: outcome.ok, error: outcome.error || '',
    written: fs.existsSync(targetPath),
    onDisk: fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : null};
}
process.stdout.write(JSON.stringify(report));
'''


class WorkflowWritePluginTest(unittest.TestCase):
    def _signed_plan(self, workspace, stacks, product=None):
        """Plan bytes signed the way the Host signs them and read back by the Host.

        The digest expression is the one ``stack.plan`` uses; ``stack.load`` is the
        production reader, so a canonicalization that drifted by so much as a
        separator would raise here instead of silently making the case green.
        """
        value = {"version": 1,
                 "product": str(product if product else workspace.parent / "Improvement"),
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
            "contradiction": {"plan": signed, "content": json.dumps(record) + "\n" + json.dumps(
                dict(record, command=entrypoint, result="FAIL")) + "\n"},
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
                               ("unsigned", "capability-plan alterado"),
                               ("contradiction", "contradice")):
            with self.subTest(case=name):
                outcome = report[name]
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(expected, outcome["error"])
                self.assertFalse(
                    outcome["written"],
                    f'{name} reached writeText: {outcome["onDisk"]!r}')

    def test_oversized_evidence_has_a_managed_home_with_its_own_caps(self):
        """D9: legitimate artifacts had nowhere to live, so the preflight archived them.

        A 4.0 MB candidate patch and a 5.8 MB formatter log were found in the
        state root as `unexpected-evidence`: real work treated as a stray file
        because a 4 KiB record cannot hold it. They now have a declared root
        with its own caps — and anything outside the state root or that root is
        still refused, so the accommodation did not widen the writable surface.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-evidence-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement'
        product.mkdir(parents=True)
        (product / 'stack.py').write_text('CANONICAL = True\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            json.dumps({'version': 1, 'product': str(product),
                        'workspace': str(workspace), 'stacks': []}))
        (workspace / 'mode-state').mkdir()
        (workspace / 'evidence').mkdir()

        cases = {
            "artifact": {"path": "Improvement-workspace/evidence/candidate-repair.patch",
                         "content": "diff --git a/x b/x\n"},
            "unsafe_name": {"path": "Improvement-workspace/evidence/../escape.log",
                            "content": "x\n"},
            "nested": {"path": "Improvement-workspace/evidence/sub/deep.log", "content": "x\n"},
            "outside_workspace": {"path": "Improvement-workspace/notes.md", "content": "x\n"},
            "into_product": {"path": "Improvement/stolen.py", "content": "x\n"},
            "too_big": {"path": "Improvement-workspace/evidence/huge.log",
                        "content": "x" * (8 * 1024 * 1024 + 1)},
            "state_still_allowed": {
                "path": "Improvement-workspace/mode-state/work-items.json",
                "content": '{"schema_version":1,"candidate":null,"items":[]}'},
        }
        (session / 'fixture.json').write_text(json.dumps({"cases": cases}))
        driver = root / 'evidence-driver.mjs'
        driver.write_text(EVIDENCE_DRIVER.replace(
            'PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run(
            [node, driver.as_posix(), session.as_posix()],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        self.assertTrue(report["artifact"]["ok"], report["artifact"])
        self.assertTrue(report["artifact"]["written"], report["artifact"])
        self.assertTrue(report["state_still_allowed"]["ok"], report["state_still_allowed"])
        # The traversal spelling is refused by the runtime that keeps `..` in
        # processPath; a driver that canonicalizes first is caught by the
        # containment check instead, which is the same refusal with a path.
        for name, expected in (("unsafe_name", "sale de"),
                               ("outside_workspace", "sale de"),
                               ("into_product", "sale de"),
                               ("too_big", "tope por fichero")):
            with self.subTest(case=name):
                outcome = report[name]
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(expected, outcome["error"])
                self.assertFalse(outcome["written"], f'{name} reached writeText')
        # A nested path is not a valid artifact name: the cap counts files
        # directly under the root, so a subdirectory would escape that count.
        self.assertFalse(report["nested"]["ok"], report["nested"])
        self.assertIn("no seguro", report["nested"]["error"])
        self.assertEqual((product / 'stack.py').read_text(), 'CANONICAL = True\n')
        self.assertFalse((workspace / 'notes.md').exists())

    def test_finding_anchor_is_located_by_the_tool_not_claimed_by_the_mode(self):
        """The one field of a finding a machine can check.

        Evidence was prose inside `summary`, so `archivo:línea` was a claim
        about itself. The finding now quotes a fragment verbatim and names the
        file; the tool locates that quote and writes the line. A quote that does
        not appear, or that appears twice, is refused instead of resolved —
        open-code-review declines for exactly the same reason, because an
        anchor that cannot be placed ends up looking located while pointing at
        an unrelated line. A finding about something with no location carries no
        anchor, which is honest and countable.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-anchor-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement'
        (product / 'src').mkdir(parents=True)
        (product / 'src' / 'api.py').write_text(
            'import os\n\n\ndef create_user(payload):\n    return payload\n\n\n'
            'def helper():\n    return 1\n\n\ndef other():\n    return 1\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / 'mode-state').mkdir()
        signed = self._signed_plan(workspace, [], product=str(product))

        base = 'a' * 40
        record = {'finding_id': 'A-01', 'base_revision': base, 'severity': 'HIGH',
                  'summary': 'Missing validation', 'status': 'OPEN'}

        def with_evidence(**evidence):
            return json.dumps({**record, 'evidence': {'path': 'src/api.py', **evidence}},
                              ensure_ascii=False) + '\n'

        cases = {
            "resolves": with_evidence(excerpt='def create_user(payload):'),
            "resolves_multiline": with_evidence(
                excerpt='def helper():\n    return 1'),
            "absent": with_evidence(excerpt='def deleted_user(payload):'),
            "ambiguous": with_evidence(excerpt='    return 1'),
            "no_anchor": json.dumps(record) + '\n',
            "line_claimed": with_evidence(
                excerpt='def helper():\n    return 1', line=8),
            "unknown_field": json.dumps({**record, 'evidence': {
                'path': 'src/api.py', 'excerpt': 'def helper():', 'confidence': 'alta'}},
                ensure_ascii=False) + '\n',
            "path_escape": with_evidence(excerpt='import os') .replace(
                '"src/api.py"', '"../Improvement/src/api.py"'),
        }
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(signed)
        (session / 'fixture.json').write_text(json.dumps(cases))
        driver = root / 'anchor-driver.mjs'
        driver.write_text(ANCHOR_DRIVER.replace(
            'PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run(
            [node, driver.as_posix(), session.as_posix()],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        anchored = json.loads(report["resolves"]["onDisk"])["evidence"]
        self.assertTrue(report["resolves"]["ok"], report["resolves"])
        self.assertEqual(anchored["line"], 4)
        self.assertIs(anchored["located"], True)
        # The model wrote path and excerpt; the line in the bytes that landed is
        # the tool's, and the record is re-serialized in canonical field order.
        self.assertEqual(
            json.loads(report["resolves"]["onDisk"])["evidence"]["excerpt"],
            "def create_user(payload):")
        multiline = json.loads(report["resolves_multiline"]["onDisk"])["evidence"]
        self.assertEqual(multiline["line"], 8)

        # No anchor is allowed and stays visibly unanchored rather than being
        # padded with an invented location.
        unanchored = json.loads(report["no_anchor"]["onDisk"])
        self.assertNotIn("evidence", unanchored)

        for name, expected in (("absent", "no aparece"),
                               ("ambiguous", "veces"),
                               ("line_claimed", "los calcula la herramienta"),
                               ("unknown_field", "exactamente path y excerpt"),
                               ("path_escape", "sale del producto")):
            with self.subTest(case=name):
                outcome = report[name]
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(expected, outcome["error"])
                self.assertFalse(
                    outcome["written"],
                    f'{name} reached writeText: {outcome["onDisk"]!r}')

    def test_fingerprint_identifies_the_code_not_the_wording(self):
        """The same defect described twice has to be countable as one.

        The dedupe key is `(finding_id, base_revision)`, so a re-audit that
        describes the same line differently produces a second record and the
        queue grows a duplicate. The fingerprint is computed from the quoted
        code — path plus excerpt — never from the wording, and it is the tool
        that computes it, so it cannot be reused to smuggle in a different
        identity. `cause` and `prevention` are the other half of a rich
        finding: why the defect exists and what would stop it coming back,
        both bounded, both checked against the record cap at write time rather
        than dropped by the next preflight.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-rich-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement'
        (product / 'src').mkdir(parents=True)
        (product / 'src' / 'api.py').write_text(
            'def create_user(payload):\n    return payload\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / 'mode-state').mkdir()
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            self._signed_plan(workspace, [], product=str(product)))

        base = 'a' * 40
        record = {'finding_id': 'A-01', 'base_revision': base, 'severity': 'HIGH',
                  'summary': 'Missing validation', 'status': 'OPEN',
                  'cause': 'The handler trusts the request body',
                  'prevention': 'A schema check on the route',
                  'evidence': {'path': 'src/api.py', 'excerpt': 'def create_user(payload):'}}
        cases = {
            "rich": json.dumps(record, ensure_ascii=False) + '\n',
            "same_code_other_wording": json.dumps({
                **{k: v for k, v in record.items() if k != 'summary'},
                'summary': 'The endpoint accepts anything'}, ensure_ascii=False) + '\n',
            "fingerprint_claimed": json.dumps({
                **record, 'evidence': {**record['evidence'], 'fingerprint': 'e' * 64}},
                ensure_ascii=False) + '\n',
            "cause_too_long": json.dumps({**record, 'cause': 'x' * 257},
                                         ensure_ascii=False) + '\n',
            "record_over_cap": json.dumps({**record, 'summary': 'x' * 4_200},
                                          ensure_ascii=False) + '\n',
        }
        (session / 'fixture.json').write_text(json.dumps(cases))
        driver = root / 'rich-driver.mjs'
        driver.write_text(ANCHOR_DRIVER.replace('PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run([node, driver.as_posix(), session.as_posix()],
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        landed = json.loads(report["rich"]["onDisk"])
        fingerprint = landed["evidence"]["fingerprint"]
        self.assertRegex(fingerprint, r'^[0-9a-f]{64}$')
        self.assertEqual(landed["cause"], record["cause"])
        self.assertEqual(landed["prevention"], record["prevention"])
        # Rewording the summary does not change what the code is.
        self.assertEqual(
            json.loads(report["same_code_other_wording"]["onDisk"])["evidence"]["fingerprint"],
            fingerprint)
        for name, expected in (("fingerprint_claimed", "los calcula la herramienta"),
                               ("cause_too_long", "cause debe ser texto"),
                               ("record_over_cap", "tope del registro")):
            with self.subTest(case=name):
                self.assertFalse(report[name]["ok"], report[name])
                self.assertIn(expected, report[name]["error"])
                self.assertFalse(report[name]["written"])

    def test_a_defect_the_memory_already_closed_is_marked_as_a_repeat(self):
        """E2 closed the ledger; nothing read it, so the auditor repeated itself.

        The Host writes `episodes-index.json` and stamps a fingerprint on every
        finding, and before this the two never met: the write path computed the
        exact key the memory is indexed by and dropped it on the floor. An
        auditor met the same defect every session, produced a finding every
        session, and the queue grew a duplicate each time — the most expensive
        failure a framework like this has, invisible because the ledger itself
        worked.

        So the repeat is stamped by the tool, from the fingerprint it already
        computes, and the memory is read on the write path. A mode that writes
        `prior_episode` is refused: the one claim the memory has to make cannot
        be the mode's. An absent index is an empty memory, not a refusal — a
        workspace that never closed a unit has nothing to remember. An index
        that is there and unreadable is refused, because the alternative is
        guessing "new", which is the answer that produces the duplicates.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        import hashlib
        root = Path(tempfile.mkdtemp(prefix='workflow-write-memory-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement'
        (product / 'src').mkdir(parents=True)
        (product / 'src' / 'api.py').write_text(
            'def create_user(payload):\n    return payload\n'
            '\n\ndef delete_user(user_id):\n    return None\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / 'mode-state').mkdir()
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            self._signed_plan(workspace, [], product=str(product)))

        def fingerprint(excerpt):
            return hashlib.sha256(
                f"src/api.py\n{excerpt}".encode('utf-8')).hexdigest()

        quoted = 'def create_user(payload):'
        other = 'def delete_user(user_id):'
        base = 'a' * 40

        def finding(**overrides):
            record = {'finding_id': 'A-01', 'base_revision': base, 'severity': 'HIGH',
                      'summary': 'Missing validation', 'status': 'OPEN',
                      'evidence': {'path': 'src/api.py', 'excerpt': quoted}}
            return json.dumps({**record, **overrides}, ensure_ascii=False) + '\n'

        def index_for(signature, verdict='PASS', unit='U-7'):
            return json.dumps({'version': 1, 'signatures': {signature: [
                {'unit': unit, 'verdict': verdict, 'evidence': 'verification.jsonl#U-7',
                 'repair': 'Validate the payload against the route schema'}]}})

        cases = {
            # The memory has this exact code closed by a proven repair.
            "repeat": {'index': index_for(fingerprint(quoted)),
                       'content': finding(summary='Still no validation on create')},
            # Same defect, different wording: the fingerprint is the code, so
            # this is still a repeat and not a second record.
            "repeat_other_wording": {'index': index_for(fingerprint(quoted)),
                                     'content': finding(summary='The endpoint accepts anything')},
            # Different code: the memory has never seen it.
            "novel": {'index': index_for(fingerprint(quoted)),
                      'content': finding(evidence={'path': 'src/api.py', 'excerpt': other})},
            # No index at all: nothing to remember, and the audit still lands.
            "empty_memory": {'index': None, 'content': finding()},
            # An attempt that did not verify is not remembered, so a FAIL entry
            # is not a reason to call the defect closed.
            "unproven_episode": {'index': index_for(fingerprint(quoted), verdict='FAIL'),
                                 'content': finding()},
            # The mode claiming its own history.
            "claimed_prior_episode": {
                'index': index_for(fingerprint(quoted)),
                'content': finding(evidence={'path': 'src/api.py', 'excerpt': quoted,
                                             'prior_episode': {'unit': 'U-1'}})},
            # A memory the tool cannot read is a memory it would have to guess.
            "corrupt_index": {'index': '{not json', 'content': finding()},
            "shapeless_index": {'index': json.dumps({'version': 1}), 'content': finding()},
        }
        (session / 'fixture.json').write_text(json.dumps(cases))
        driver = root / 'memory-driver.mjs'
        driver.write_text(MEMORY_DRIVER.replace('PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run([node, driver.as_posix(), session.as_posix()],
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        for name in ("repeat", "repeat_other_wording"):
            with self.subTest(case=name):
                self.assertTrue(report[name]["ok"], report[name])
                landed = json.loads(report[name]["onDisk"])
                self.assertEqual(landed["evidence"]["prior_episode"]["unit"], "U-7")
                self.assertEqual(landed["evidence"]["prior_episode"]["repair"],
                                 'Validate the payload against the route schema')
                self.assertRegex(landed["evidence"]["fingerprint"], r'^[0-9a-f]{64}$')
        for name in ("novel", "empty_memory", "unproven_episode"):
            with self.subTest(case=name):
                self.assertTrue(report[name]["ok"], report[name])
                self.assertNotIn("prior_episode", json.loads(report[name]["onDisk"])["evidence"])
        for name, expected in (("claimed_prior_episode", "los calcula la herramienta"),
                               ("corrupt_index", "no es JSON"),
                               ("shapeless_index", "sin tabla de firmas")):
            with self.subTest(case=name):
                self.assertFalse(report[name]["ok"], report[name])
                self.assertIn(expected, report[name]["error"])
                self.assertFalse(report[name]["written"])

    def test_a_live_lease_from_another_session_denies_the_replacement(self):
        """D1: the write was never atomic, and a concurrent one could interleave.

        Nothing the filesystem backend offers turns a five-file replacement
        into a transaction, so the declared non-atomicity across files stays.
        What the lease closes is the narrower failure it made possible: one
        session replacing a file another session is replacing, the second
        discarding a write it never saw. It is taken before writeText, released
        after it, expires so a dead session cannot wedge the state, and a
        session that cannot be identified takes no lease rather than a shared
        one.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-lease-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        product = session / 'Improvement'
        product.mkdir(parents=True)
        (product / 'stack.py').write_text('CANONICAL = True\n')
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            self._signed_plan(workspace, [], product=str(product)))
        (workspace / 'mode-state').mkdir()
        (workspace / 'evidence').mkdir()

        driver = root / 'lease-driver.mjs'
        driver.write_text(LEASE_DRIVER.replace('PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run([node, driver.as_posix(), session.as_posix()],
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        self.assertFalse(report["held_by_other"]["ok"], report["held_by_other"])
        self.assertIn("otra sesión", report["held_by_other"]["error"])
        # The refused write left the holder's lease alone.
        self.assertEqual(report["heldError"], "other-session")
        # An expired lease is takeable: a session that died holding one must
        # not wedge the state forever.
        self.assertTrue(report["expired"]["ok"], report["expired"])
        # The holder may re-enter its own write.
        self.assertTrue(report["held_by_self"]["ok"], report["held_by_self"])
        self.assertEqual(report["leaseAfterWrite"]["state"], "released")
        # The evidence root is not state, so no lease is taken for it.
        self.assertTrue(report["artifact"]["ok"], report["artifact"])
        self.assertFalse(report["artifactLease"])
        # No session identity, no lease: a lock everybody holds is no lock.
        self.assertTrue(report["anonymous"]["ok"], report["anonymous"])
        self.assertEqual((product / 'stack.py').read_text(), 'CANONICAL = True\n')

    def test_audit_handoff_must_name_every_open_finding_at_its_base(self):
        """A1: `persisted_count` was a claim about itself with nothing behind it.

        The contract asks the auditor to report how much it persisted, but
        nothing compared that number with `findings.jsonl`: a turn that
        persisted nothing could still answer with a count. Syncify is the case
        that motivated this — six consecutive findings had a work item and no
        repair handoff covering them. The tool now refuses, before writeText, a
        handoff that names an unpersisted finding or omits one the state leaves
        OPEN at the same base.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the plugin module')
        root = Path(tempfile.mkdtemp(prefix='workflow-write-handoff-'))
        self.addCleanup(shutil.rmtree, root, True)
        session = root / 'selftest'
        (session / 'Improvement' / 'scripts').mkdir(parents=True)
        workspace = session / 'Improvement-workspace'
        (workspace / '.dsh-managed').mkdir(parents=True)
        (workspace / '.dsh-managed' / 'capability-plan.json').write_text(
            json.dumps({'version': 1, 'workspace': str(workspace), 'stacks': []}))
        (workspace / 'mode-state').mkdir()

        base = 'a' * 40
        other = 'b' * 40
        prompt = 'Repara los hallazgos de la auditoría; no publiques.'
        repair_prompt = 'Repara A-01; no publiques.'
        findings = ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in (
            {"finding_id": "A-01", "base_revision": base, "severity": "HIGH",
             "summary": "Missing validation", "status": "OPEN"},
            {"finding_id": "A-02", "base_revision": base, "severity": "LOW",
             "summary": "Stale doc", "status": "OPEN"},
            {"finding_id": "A-03", "base_revision": base, "severity": "MEDIUM",
             "summary": "Already fixed", "status": "RESOLVED"},
            {"finding_id": "B-01", "base_revision": other, "severity": "HIGH",
             "summary": "Other base", "status": "OPEN"},
        ))

        def handoff(ids, base_revision=base, next_prompt=prompt, **extra):
            return json.dumps(dict({
                "handoff_id": "audit-1", "base_revision": base_revision,
                "finding_ids": ids, "next_prompt": next_prompt}, **extra),
                ensure_ascii=False) + '\n'

        cases = {
            "complete": {"findings": findings,
                         "content": handoff(["A-01", "A-02"])},
            "uncovered": {"findings": findings,
                          "content": handoff(["A-01"])},
            "unpersisted": {"findings": findings,
                            "content": handoff(["A-01", "A-02", "A-03"])},
            "other_base": {"findings": findings,
                           "content": handoff([], base_revision=other)},
            "extra_field": {"findings": findings,
                            "content": handoff(["A-01", "A-02"], path="/abs/candidate")},
            "repair_partial": {"findings": findings,
                               "content": handoff(["A-01"], next_prompt=repair_prompt)},
        }
        (session / 'fixture.json').write_text(json.dumps(cases))
        driver = root / 'handoff-driver.mjs'
        driver.write_text(HANDOFF_DRIVER.replace(
            'PLUGIN_PATH', (PLUGIN).as_posix()))
        finished = subprocess.run(
            [node, driver.as_posix(), session.as_posix()],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        report = json.loads(finished.stdout)

        self.assertTrue(report["complete"]["ok"], report["complete"])
        self.assertTrue(report["complete"]["written"], report["complete"])
        for name, expected in (("uncovered", "sin nombrar: A-02"),
                               ("unpersisted", "no OPEN: A-03"),
                               ("extra_field", "schema estricto")):
            with self.subTest(case=name):
                outcome = report[name]
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn(expected, outcome["error"])
                self.assertFalse(
                    outcome["written"],
                    f'{name} reached writeText: {outcome["onDisk"]!r}')
        # A repair handoff names the findings it took, not the whole open set:
        # the coverage rule is the audit claim, and refusing partial repair
        # would strand every candidate that cannot close the queue at once.
        self.assertTrue(report["repair_partial"]["ok"], report["repair_partial"])
        # Coverage is scoped to the handoff's own base: an audit that declares
        # another revision must answer for that revision's open set, not the
        # one it audited a moment ago.
        self.assertFalse(report["other_base"]["ok"], report["other_base"])
        self.assertIn("sin nombrar: B-01", report["other_base"]["error"])

    def test_same_mode_escalation_writes_and_outside_denied(self):
        runtime = __import__('os').environ.get('DSH_MODULE_ROOT')
        if not runtime:
            self.skipTest('Set DSH_MODULE_ROOT to installed runtime; no installation/fallback')
        # This probe mounts a per-agent preset row, and that plugin
        # (`@deepseek-ai/dsh-agent-preset`) only ships from 0.1.7-alpha.1 on. An
        # older runtime cannot run the probe at all, so say which version is
        # needed instead of failing on a module Node cannot resolve.
        preset_plugin = Path(runtime) / '@deepseek-ai' / 'dsh-agent-preset' / 'package.json'
        if not preset_plugin.is_file():
            self.skipTest(
                'runtime lacks @deepseek-ai/dsh-agent-preset (needs 0.1.7-alpha.1+); '
                f'found {Path(runtime).name}')
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

    def test_selfcheck_script_passes_its_own_checks(self):
        """The self-check runs here, so it cannot rot into a script nobody runs.

        `verify-workflow-write.mjs` holds 51 checks over the plugin, including
        the managed-plan integrity and schema-strictness denials. Nothing invoked
        it, so it was free to drift. It needs `node` plus the runtime's
        `dsh-tools`; without that it now reports SKIP for the M9 bash sweep and
        still asserts the 33 checks that only need a simulated context.
        """
        node = shutil.which('node')
        if not node:
            self.skipTest('Set node on PATH to drive the self-check')
        env = dict(os.environ)
        runtime_root = env.get('DSH_MODULE_ROOT')
        tools_index = None
        if runtime_root:
            candidate = Path(runtime_root) / '@deepseek-ai/dsh-tools/lib/index.js'
            if candidate.is_file():
                tools_index = str(candidate)
        if tools_index is None:
            self.skipTest('Set DSH_MODULE_ROOT to a runtime with @deepseek-ai/dsh-tools')
        env['DSH_TOOLS_INDEX'] = tools_index
        bash_index = Path(runtime_root) / '@deepseek-ai/dsh-tool-bash/lib/index.js'
        if bash_index.is_file():
            env['DSH_TOOL_BASH'] = str(bash_index)
        else:
            env.pop('DSH_TOOL_BASH', None)
        finished = subprocess.run(
            [node, str(FRAMEWORK / 'scripts/dsh-plugins/verify-workflow-write.mjs')],
            capture_output=True, text=True, timeout=180, env=env)
        output = finished.stdout + finished.stderr
        self.assertEqual(finished.returncode, 0, output[-3000:])
        self.assertIn('TODO OK', output)
        self.assertNotIn('\nFAIL  ', output, output[-2000:])
        # The 33 context-only checks must run with node alone; losing them to a
        # missing runtime path is how verification goes quiet.
        self.assertGreaterEqual(output.count('PASS  '), 33, output[-2000:])


if __name__ == '__main__':
    unittest.main()
