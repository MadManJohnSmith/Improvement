// Run with DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_skill_root.mjs [workspace]
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, cp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

assert(process.env.DSH_MODULE_ROOT?.startsWith('/'), 'Set absolute DSH_MODULE_ROOT (installed node_modules)');
const require = createRequire(join(process.env.DSH_MODULE_ROOT, 'package.json'));
const load = name => import(require.resolve('@deepseek-ai/' + name));
const temporary = await mkdtemp(join(tmpdir(), 'dsh-skill-root-'));
const workspace = process.argv[2] ? resolve(process.argv[2]) : join(temporary, 'workspace');
const { Context } = await load('cordis');
const { createScope } = await load('dsh-scope');
const ctx = new Context();
try {
  if (!process.argv[2]) {
    await mkdir(join(workspace, '.agents'), { recursive: true });
    await cp(fileURLToPath(new URL('../skills', import.meta.url)), join(workspace, '.agents/skills'), { recursive: true });
  }
  ctx.plugin((await load('dsh-system-prompt')).default, {});
  ctx.plugin((await load('dsh-tools')).default, {});
  ctx.plugin((await load('dsh-skill')).default, {});
  await new Promise(resolve => setImmediate(resolve));
  const agent = { session: { header: { cwd: workspace } } };
  const scope = createScope(ctx.inject(['skills', 'tools'], () => {}).ctx, agent);
  // ponytail: native preset services without a full Host/LLM; GUI acceptance remains separate.
  (await load('dsh-skill-filesystem')).apply(scope.ctx, {
    watch: false, dshHome: join(temporary, 'dsh-home'), agentsHome: join(temporary, 'agents-home'),
  });
  (await load('dsh-tool-skill')).apply(scope.ctx);
  assert.equal((await ctx.skills.list({ cwd: workspace })).length, 0, 'provider must remain scoped');
  const parent = await ctx.skills.list({ cwd: dirname(workspace), scope: agent });
  assert.equal(parent.length, 0, 'parent cwd must not discover child workspace');
  const skills = await ctx.skills.list({ cwd: workspace, scope: agent });
  assert.equal(skills.length, 5);
  for (const skill of skills) {
    assert.equal(skill.source, 'project-agents');
    assert.equal(skill.provider, 'filesystem');
    const base = join(workspace, '.agents/skills', skill.name);
    assert.equal(skill.resourceBase.path, base);
    const source = await readFile(join(base, 'SKILL.md'), 'utf8');
    const result = await ctx.tools.execute({
      name: 'skill', arguments: { name: skill.name }, agent,
      callId: skill.name, signal: new AbortController().signal,
    });
    assert.equal(result.isError, false);
    assert.equal(result.value.provider, 'filesystem');
    assert.equal(result.value.resourceBase.path, base);
    assert.equal(result.value.content, source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim());
    assert(result.content.some(part => part.text?.includes(result.value.content)));
    console.log(JSON.stringify({ name: skill.name, source: skill.source, origin: base,
      sha256: createHash('sha256').update(source).digest('hex'), loaded: true }));
  }
  await scope.dispose();
  console.log('PASS: parent=0 workspace=5; scoped registry and native tools.execute; no models');
} finally {
  await ctx.fiber.dispose();
  await rm(temporary, { recursive: true, force: true });
}
