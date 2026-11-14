// DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_skill_root.mjs
//
// Optional external evidence, never a core-suite dependency: the failure this
// guards was measured on a real DSH instance, so the regression is proved on
// the same loader the Host trusts. Without DSH_MODULE_ROOT the test exits as a
// documented skip rather than as a pass, so an unaudited tree cannot claim the
// contract was verified.
//
// What it proves: two project roots carrying the SAME skill names with
// DIFFERENT bodies never leak across sessions (no cache collision), each
// skill's catalog entry resolves to its own real file (skill root), a
// project-only name is discoverable, and a missing name is refused. rc.2
// fuses tool execution into the full service graph, so the check boots the
// real web profile (the sandbox-probe pattern, on the host) instead of
// hand-mounting a plugin subset; rc.2 tool results carry the served body as
// text content (no structured value), so the exact-body assertion reads the
// text parts.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createHash, createHmac } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, realpath, rm, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

assert(process.env.DSH_MODULE_ROOT?.startsWith('/'), 'Set absolute DSH_MODULE_ROOT');
const require = createRequire(join(process.env.DSH_MODULE_ROOT, 'package.json'));
const load = name => import(require.resolve('@deepseek-ai/' + name));
const yaml = await import(require.resolve('yaml'));
const framework = fileURLToPath(new URL('..', import.meta.url));

const temporary = await mkdtemp(join(tmpdir(), 'dsh-skill-root-'));
const dshHome = join(temporary, 'dsh-home');
const port = 3498;
const authority = `127.0.0.1:${port}`;
let boot;
let ok = false;
try {
  await mkdir(join(dshHome, 'sessions'), {recursive: true});
  await writeFile(join(dshHome, 'settings.yaml'),
    'llm-pi-ai:\n'
    + '  providers:\n'
    + '    fixture-provider:\n'
    + '      api: openai-completions\n'
    + '      baseURL: http://127.0.0.1:9/v1\n'
    + '      apiKeyEnv: FIXTURE_UNUSED\n'
    + '      models:\n'
    + '        - id: fixture-model\n'
    + 'agent-default-model:\n'
    + '  provider: fixture-provider\n'
    + '  model: fixture-model\n', 'utf8');

  const agents = [];
  for (const label of ['alpha', 'beta']) {
    const parent = join(temporary, label);
    const workspace = join(parent, 'private');
    const product = join(parent, 'product');
    await mkdir(product, {recursive: true});
    execFileSync('python3', ['-B', join(framework, 'scripts/onboard.py'), '--project', product,
      '--workspace', workspace, '--name', label, '--init', '--prepare-skills', '--session-root', parent],
      {cwd: temporary});
    // Different bodies under the same names detect cache leaks, plus a
    // project-only name that exists in exactly one root.
    await writeFile(join(workspace, '.agents/skills/project-onboarding/SKILL.md'),
      `---\nname: project-onboarding\ndescription: fixture\n---\nExact body ${label}\n`, 'utf8');
    const extra = join(parent, '.agents/skills', label);
    await mkdir(extra, {recursive: true});
    await writeFile(join(extra, 'SKILL.md'),
      `---\nname: ${label}\ndescription: fixture\n---\nOnly ${label}\n`, 'utf8');
    agents.push({parent, workspace, label});
  }

  // Hermetic: the profile must scan the fixture homes, not the host user's
  // real ~/.agents catalog (the bwrap probe got this isolation from launch()).
  const homeDir = join(temporary, 'home');
  await mkdir(homeDir, {recursive: true});
  process.env.HOME = homeDir;
  process.env.DSH_HOME = dshHome;
  const { runProfile } = await import(require.resolve('@deepseek-ai/dsh/lib/profile-boot.js'));
  const { loadLayeredEnv } = await load('dsh-app-boot');
  boot = await runProfile({profile: 'web', patchFiles: [],
    args: ['--host', '127.0.0.1', '--port', String(port), '--no-open'],
    environment: loadLayeredEnv('dsh')});

  function decodeB64u(v) { const p = '='.repeat((4 - (v.length % 4)) % 4); return Buffer.from(v.replaceAll('-', '+').replaceAll('_', '/') + p, 'base64'); }
  function encodeB64u(b) { return Buffer.from(b).toString('base64').replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, ''); }
  const creds = yaml.parse(await readFile(join(dshHome, '.credentials.yaml'), 'utf8'));
  const secret = decodeB64u(creds.records['client-connection/browser-session'].payload.secret);
  const now = Date.now();
  const body = encodeB64u(Buffer.from(JSON.stringify({version: 1, authority, issuedAt: now, expiresAt: now + 3600000}), 'utf8'));
  const cookieName = 'dsh-auth-' + encodeB64u(createHash('sha256').update(authority).digest());
  const cookie = `${cookieName}=v1.${body}.${encodeB64u(createHmac('sha256', secret).update(body).digest())}`;
  let seq = 0;
  const rpc = async (method, args) => {
    const res = await fetch(`http://${authority}/api/${method}`, {method: 'POST',
      headers: {'Content-Type': 'application/json', Cookie: cookie, Host: authority},
      body: JSON.stringify({type: 'client-request', rpcId: `r${seq++}`, method, payload: {args}})});
    const json = await res.json();
    return {ok: json.result?.ok === true, value: json.result?.value, error: json.result?.error};
  };
  const resultText = (result) => (result.content || []).map(p => p.text).join(' ');

  // The revisited alpha (agents[0] twice) checks the second session against a
  // root another session already loaded: no cache collision may serve beta's
  // body under alpha's name.
  for (const {parent, workspace, label} of [...agents, agents[0]]) {
    // The full profile legitimately serves the framework's own skills from
    // the global scope; what must never leak is a PROJECT-ONLY name.
    const globalNames = (await boot.ctx.skills.list({cwd: parent})).map(s => s.name);
    assert.equal(globalNames.includes(label), false,
      `the project-only skill "${label}" must not leak into the global scope`);
    const created = await rpc('session/create', {request: {cwd: parent}});
    if (!created.ok) throw new Error('session/create: ' + JSON.stringify(created.error));
    const agent = boot.ctx.agents.get(created.value.sessionId);
    assert(agent, 'the booted context must expose the created session agent');
    const skills = await boot.ctx.skills.list({cwd: parent, scope: agent});
    const byName = new Map(skills.map(skill => [skill.name, skill]));
    // The full profile also serves runtime-bundled skills (rc.2 ships dsh-doc,
    // office*): the contract under test covers the onboarded framework set
    // plus the project-only name, each resolving to THIS root's file.
    const expected = (await readdir(join(framework, 'skills'))).concat(label).sort();
    for (const name of expected) {
      const skill = byName.get(name);
      assert(skill, `expected skill ${name} missing from ${label}'s catalog`);
      assert.equal(skill.source, 'project-agents');
      const base = join(parent, '.agents/skills', name);
      const origin = name === label ? base : join(workspace, '.agents/skills', name);
      assert.equal(await realpath(base), origin, `skill root for ${label}/${name}`);
      const source = await readFile(join(origin, 'SKILL.md'), 'utf8');
      const batch = await boot.ctx.tools.execute({
        calls: [{ id: `${label}-${name}`, name: 'skill',
          arguments: JSON.stringify({ name }) }],
        agent, signal: new AbortController().signal,
      });
      const result = batch.results[0].result;
      assert.equal(result.isError, false, resultText(result).slice(0, 200));
      // The served body must be THIS root's file, not the sibling root's
      // same-named skill (the cache-leak failure the trial recorded). rc.2
      // tool results carry the body as text content, not a structured value.
      const exactBody = source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim();
      assert.ok(resultText(result).includes(exactBody),
        `the served body must come from ${origin}; served: ${resultText(result).slice(0, 200)}`);
      console.log(JSON.stringify({ project: label, name, origin,
        sha256: createHash('sha256').update(source).digest('hex'), loaded: true }));
    }
    const missingLabel = label === 'alpha' ? 'beta' : 'alpha';
    const missingBatch = await boot.ctx.tools.execute({
      calls: [{ id: `${label}-missing`, name: 'skill',
        arguments: JSON.stringify({ name: missingLabel }) }],
      agent, signal: new AbortController().signal,
    });
    const missing = missingBatch.results[0].result;
    assert.equal(missing.isError, true, `a name that exists only under the other root must be refused: ${resultText(missing).slice(0, 200)}`);
  }
  console.log('PASS: two parent roots, shared Standard skill scope, exact bodies, no cross-project discovery; no models');
  ok = true;
} catch (error) {
  console.error('FAIL: ' + String(error && error.stack || error).slice(0, 1200));
} finally {
  if (boot) await boot.shutdown.shutdown(ok ? 0 : 1);
  await rm(temporary, {recursive: true, force: true});
}
if (!ok) process.exit(1);
