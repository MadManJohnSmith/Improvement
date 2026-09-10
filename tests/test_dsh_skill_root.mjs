// DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_skill_root.mjs
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile, realpath } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

assert(process.env.DSH_MODULE_ROOT?.startsWith('/'), 'Set absolute DSH_MODULE_ROOT');
const require = createRequire(join(process.env.DSH_MODULE_ROOT, 'package.json'));
const load = name => import(require.resolve('@deepseek-ai/' + name));
const framework = fileURLToPath(new URL('..', import.meta.url));
const temporary = await mkdtemp(join(tmpdir(), 'dsh-skill-root-'));
const { Context } = await load('cordis');
const { createScope, bindScopeParent } = await load('dsh-scope');
const ctx = new Context();
try {
  const { validateEscalationArgs, approveEscalation, ESCALATION_TARGETS } = await load('dsh-sandbox');
  assert.deepEqual(ESCALATION_TARGETS, ['workspace-write', 'danger-full-access']);
  assert.doesNotThrow(() => validateEscalationArgs(undefined, undefined));
  assert.throws(() => validateEscalationArgs('workspace-write', undefined), /justification/);
  await assert.rejects(approveEscalation({ requestedMode: 'workspace-write', effectiveMode: 'workspace-write',
    justification: 'read fixture', subject: 'command' }, {}), /strictly wider/);
  ctx.plugin((await load('dsh-system-prompt')).default, {});
  ctx.plugin((await load('dsh-tools')).default, {});
  ctx.plugin((await load('dsh-skill')).default, {});
  await new Promise(resolve => setImmediate(resolve));
  const preset = {};
  const scope = createScope(ctx.inject(['skills', 'tools'], () => {}).ctx, preset);
  const presetFile = join(dirname(require.resolve('@deepseek-ai/dsh-agent-presets')), '../presets/standard/agent.cordis.yml');
  const text = await readFile(presetFile, 'utf8');
  // ponytail: mount actual Standard skill rows, not full Host/LLM; GUI acceptance is separate.
  for (const id of ['skill-filesystem', 'tool-skill']) {
    const row = text.match(new RegExp(`^- id: ${id}\\n  name: '([^']+)'\\n`, 'm'));
    assert(row, `Standard row changed: ${id}`);
    (await import(require.resolve(row[1]))).apply(scope.ctx, id === 'skill-filesystem' ? {
      watch: false, dshHome: join(temporary, 'dsh-home'), agentsHome: join(temporary, 'agents-home'),
    } : {});
  }
  const agents = [];
  for (const label of ['alpha', 'beta']) {
    const parent = join(temporary, label);
    const workspace = join(parent, 'private');
    const product = join(parent, 'product');
    await mkdir(product, { recursive: true });
    execFileSync('python3', ['-B', join(framework, 'scripts/onboard.py'), '--project', product,
      '--workspace', workspace, '--name', label, '--init', '--prepare-skills', '--session-root', parent]);
    // Different bodies under the same names detect cache leaks, plus a project-only name.
    await writeFile(join(workspace, '.agents/skills/project-onboarding/SKILL.md'),
      `---\nname: project-onboarding\ndescription: fixture\n---\nExact body ${label}\n`);
    const extra = join(parent, '.agents/skills', label);
    await mkdir(extra);
    await writeFile(join(extra, 'SKILL.md'), `---\nname: ${label}\ndescription: fixture\n---\nOnly ${label}\n`);
    const agent = { session: { header: { cwd: parent } } };
    bindScopeParent(agent, preset);
    agents.push({ agent, parent, workspace, label });
  }
  for (const { agent, parent, workspace, label } of [...agents, agents[0]]) {
    assert.equal((await ctx.skills.list({ cwd: parent })).length, 0, 'no global provider');
    const skills = await ctx.skills.list({ cwd: parent, scope: agent });
    const expected = (await readdir(join(framework, 'skills'))).concat(label).sort();
    assert.deepEqual(skills.map(skill => skill.name).sort(), expected);
    for (const skill of skills) {
      assert.equal(skill.source, 'project-agents');
      const base = join(parent, '.agents/skills', skill.name);
      const origin = skill.name === label ? base : join(workspace, '.agents/skills', skill.name);
      assert.equal(await realpath(base), origin);
      const source = await readFile(join(origin, 'SKILL.md'), 'utf8');
      const result = await ctx.tools.execute({ name: 'skill', arguments: { name: skill.name }, agent,
        callId: `${label}-${skill.name}`, signal: new AbortController().signal });
      assert.equal(result.isError, false);
      assert.equal(result.value.provider, 'filesystem');
      assert.equal(result.value.resourceBase.path, base);
      assert.equal(result.value.content, source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim());
      assert(result.content.some(part => part.text?.includes(result.value.content)));
      console.log(JSON.stringify({ project: label, name: skill.name, origin,
        sha256: createHash('sha256').update(source).digest('hex'), loaded: true }));
    }
    const missing = await ctx.tools.execute({ name: 'skill', arguments: { name: label === 'alpha' ? 'beta' : 'alpha' },
      agent, callId: 'cross-project', signal: new AbortController().signal });
    assert.equal(missing.isError, true);
  }
  await scope.dispose();
  console.log('PASS: two parent roots, shared Standard skill scope, exact bodies, no cross-project discovery; no models');
} finally {
  await ctx.fiber.dispose();
  await rm(temporary, { recursive: true, force: true });
}
