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
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

const dshModuleRoot = process.env.DSH_MODULE_ROOT;
if (!dshModuleRoot?.startsWith('/')) {
  console.log('SKIP: DSH_MODULE_ROOT not set; the real DSH skill loader was not consulted');
  process.exit(0);
}
const require = createRequire(join(dshModuleRoot, 'package.json'));
const load = name => import(require.resolve('@deepseek-ai/' + name));

const temporary = await mkdtemp(join(tmpdir(), 'dsh-frontmatter-'));
const { Context } = await load('cordis');
const { createScope, bindScopeParent } = await load('dsh-scope');
const ctx = new Context();
try {
  ctx.plugin((await load('dsh-system-prompt')).default, {});
  ctx.plugin((await load('dsh-tools')).default, {});
  ctx.plugin((await load('dsh-skill')).default, {});
  await new Promise(resolve => setImmediate(resolve));
  const preset = {};
  const scope = createScope(ctx.inject(['skills', 'tools'], () => {}).ctx, preset);
  // Mount the real roster the two Standard rows carry: the filesystem provider
  // that parses frontmatter, and the tool that serves a skill by name. No
  // preset file is read, so this does not track a YAML row that DSH may reorder.
  (await load('dsh-skill-filesystem')).apply(scope.ctx, {
    watch: false, dshHome: join(temporary, 'dsh-home'), agentsHome: join(temporary, 'agents-home'),
  });
  (await load('dsh-tool-skill')).apply(scope.ctx, {});

  // Same loader, same Standard rows, only the description scalar differs: the
  // plain one carries ': ' and the quoted one carries the identical text.
  const cases = [
    { label: 'plain', description: 'Modo auditor del proyecto fixture: contrato operativo' },
    { label: 'quoted', description: JSON.stringify(
      'Modo auditor del proyecto fixture: contrato operativo') },
  ];
  const agents = [];
  for (const { label, description } of cases) {
    const parent = join(temporary, label);
    await mkdir(join(parent, '.agents/skills', label), { recursive: true });
    await writeFile(join(parent, '.agents/skills', label, 'SKILL.md'),
      `---\nname: ${label}\ndescription: ${description}\n---\nExact body ${label}\n`);    const agent = { session: { header: { cwd: parent } } };
    bindScopeParent(agent, preset);
    agents.push({ agent, parent, label });
  }

  for (const { agent, parent, label } of agents) {
    const skills = await ctx.skills.list({ cwd: parent, scope: agent });
    const listed = skills.map(skill => skill.name).includes(label);
    const loaded = await ctx.tools.execute({ name: 'skill', arguments: { name: label }, agent,
      callId: `${label}-skill`, signal: new AbortController().signal });
    console.log(JSON.stringify({ scalar: label, listed, isError: loaded.isError === true }));
    if (label === 'plain') {
      // Dropped: absent from the catalog, and the tool refuses the name it
      // would otherwise serve. The catalog is empty, which is the failure the
      // external trial recorded: no error reaches the operator.
      assert.equal(listed, false, 'an unquoted ": " must be dropped, not loaded');
      assert.equal(loaded.isError, true, 'DSH must not serve a discarded skill');
    } else {
      const listedSkill = skills.find(skill => skill.name === label);
      assert.equal(listed, true, 'a quoted description must load');
      assert.equal(loaded.isError, false, loaded);
      assert.equal(loaded.value.provider, 'filesystem');
      const origin = join(parent, '.agents/skills', label);
      assert.equal(loaded.value.resourceBase.path, origin);
      // The exact text, colon and space intact, is what the catalog advertises.
      assert.equal(listedSkill.description,
        'Modo auditor del proyecto fixture: contrato operativo');
      const source = await readFile(join(origin, 'SKILL.md'), 'utf8');
      const body = source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trim();
      assert.equal(loaded.value.content, body, 'the skill tool must return the exact body');
    }
  }
  console.log('PASS: real DSH drops the plain ": " scalar and loads the quoted one');
} finally {
  await ctx.fiber.dispose();
  await rm(temporary, { recursive: true, force: true });
}
