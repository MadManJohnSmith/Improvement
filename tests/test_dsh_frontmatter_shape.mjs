// DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_frontmatter_shape.mjs
//
// Optional external evidence, never a core-suite dependency: the failure this
// guards was measured on a real DSH instance, so the regression is proved on
// the same loader the Host trusts. Without DSH_MODULE_ROOT the test exits as a
// documented skip rather than as a pass, so an unaudited tree cannot claim the
// contract was verified.
//
// What it proves: an unquoted ': ' in a description makes the real DSH
// filesystem provider drop the skill silently, while a JSON-quoted description
// loads and the skill tool returns its exact body. Host's fail-closed
// frontmatter rule is written against exactly this measured behaviour.
//
// rc.2 fuses tool execution into the full service graph (the skill tool
// resolves the agent's working directory through working-directory → fs →
// session machinery), so hand-mounting a plugin subset no longer satisfies
// the graph. The check boots the real web profile the same way the sandbox
// probe does — on the host, against a fixture DSH home — and exercises the
// loader through the booted context. rc.2 tool results carry the served body
// as text content (no structured value), so the exact-body assertion reads
// the text parts.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createHash, createHmac } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dshModuleRoot = process.env.DSH_MODULE_ROOT;
if (!dshModuleRoot?.startsWith('/')) {
  console.log('SKIP: DSH_MODULE_ROOT not set; the real DSH skill loader was not consulted');
  process.exit(0);
}
const require = createRequire(join(dshModuleRoot, 'package.json'));
const load = name => import(require.resolve('@deepseek-ai/' + name));
const yaml = await import(require.resolve('yaml'));

const temporary = await mkdtemp(join(tmpdir(), 'dsh-frontmatter-'));
const dshHome = join(temporary, 'dsh-home');
const port = 3497;
const authority = `127.0.0.1:${port}`;
let boot;
let ok = false;
try {
  // Fixture DSH home: a keyless provider placeholder (no request is made) and
  // the two skill cases under the session cwd's .agents/skills — one plain
  // scalar (carries ': ') and one JSON-quoted twin with identical text.
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
  const cwdParent = join(temporary, 'cwd');
  const cases = [
    { label: 'plain', description: 'Modo auditor del proyecto fixture: contrato operativo' },
    { label: 'quoted', description: JSON.stringify(
      'Modo auditor del proyecto fixture: contrato operativo') },
  ];
  for (const { label, description } of cases) {
    await mkdir(join(cwdParent, label, '.agents/skills', label), {recursive: true});
    await writeFile(join(cwdParent, label, '.agents/skills', label, 'SKILL.md'),
      `---\nname: ${label}\ndescription: ${description}\n---\nExact body ${label}\n`, 'utf8');
  }

  process.env.DSH_HOME = dshHome;
  const { runProfile } = await import(require.resolve('@deepseek-ai/dsh/lib/profile-boot.js'));
  const { loadLayeredEnv } = await load('dsh-app-boot');
  boot = await runProfile({profile: 'web', patchFiles: [],
    args: ['--host', '127.0.0.1', '--port', String(port), '--no-open'],
    environment: loadLayeredEnv('dsh')});

  // Browser-trust cookie computed from the boot-created credentials, exactly
  // like the sandbox probe: the /api fence admits this derived identity.
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
    const raw = await res.text();
    if (process.env.DEBUG_RC2) console.error(`RPC ${method}: status=${res.status} ctype=${res.headers.get('content-type')} raw=${raw.slice(0, 120)}`);
    const json = JSON.parse(raw);
    return {ok: json.result?.ok === true, value: json.result?.value, error: json.result?.error};
  };
  const resultText = (result) => (result.content || []).map(p => p.text).join(' ');

  for (const { label, description } of cases) {
    const cwd = join(cwdParent, label);
    const created = await rpc('session/create', {request: {cwd}});
    if (!created.ok) throw new Error('session/create: ' + JSON.stringify(created.error));
    const agent = boot.ctx.agents.get(created.value.sessionId);
    assert(agent, 'the booted context must expose the created session agent');

    const skills = await boot.ctx.skills.list({ cwd, scope: agent });
    const listed = skills.map(skill => skill.name).includes(label);
    const batch = await boot.ctx.tools.execute({
      calls: [{ id: `${label}-skill`, name: 'skill',
        arguments: JSON.stringify({ name: label }) }],
      agent, signal: new AbortController().signal,
    });
    const loaded = batch.results[0].result;

    if (label === 'plain') {
      // Dropped: absent from the catalog, and the tool refuses the name it
      // would otherwise serve. The catalog is empty, which is the failure the
      // external trial recorded: no error reaches the operator.
      assert.equal(listed, false, 'an unquoted ": " must be dropped, not loaded');
      assert.equal(loaded.isError, true, 'DSH must not serve a discarded skill');
    } else {
      assert.equal(listed, true, 'a quoted description must load');
      const listedSkill = skills.find(skill => skill.name === label);
      assert.equal(listedSkill.description,
        'Modo auditor del proyecto fixture: contrato operativo');
      assert.equal(loaded.isError, false, resultText(loaded).slice(0, 200));
      // The exact text, colon and space intact, is what the tool serves.
      const origin = join(cwdParent, label, '.agents/skills', label);
      const source = await readFile(join(origin, 'SKILL.md'), 'utf8');
      const exactBody = source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim();
      const served = resultText(loaded);
      assert.ok(served.includes(exactBody),
        `the skill tool must return the exact body; served: ${served.slice(0, 200)}`);
      void description;
    }
  }
  console.log('PASS: real DSH drops the plain ": " scalar and loads the quoted one');
  ok = true;
} catch (error) {
  console.error('FAIL: ' + String(error && error.stack || error).slice(0, 1200));
} finally {
  if (boot) await boot.shutdown.shutdown(ok ? 0 : 1);
  await rm(temporary, {recursive: true, force: true});
}
if (!ok) process.exit(1);
