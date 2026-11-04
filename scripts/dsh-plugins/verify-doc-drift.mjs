/**
 * verify-doc-drift: regresión offline del plugin doc-drift (ADR 0002).
 *
 * Sin runtime DSH: un ctx simulado registra los hooks reales del plugin y el
 * motor real (`scripts/drift.py`) evalúa un repositorio Git sintético en un
 * directorio temporal. Cubre la lógica determinista:
 *
 *   - clasificación de un reporte en close/repin/sync;
 *   - cierre limpio con re-ancla silenciosa de la línea base;
 *   - bloqueo ante deriva de contrato con directiva inyectada;
 *   - confinamiento de escritura a los .md afectados;
 *   - certificación tras la edición documental (re-ancla y libera);
 *   - fail-closed cuando el motor no puede resolver el CLI.
 *
 * Requiere node, python3 y git. Sin ellos sale 3 (skip declarado), nunca 0.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync }
  from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { apply, classify, writeAllowed } from './doc-drift.mjs';

let failures = 0;
function check(label, condition, detail = '') {
  console.log(`${condition ? 'PASS' : 'FAIL'}  ${label}${detail ? `  -> ${detail}` : ''}`);
  if (!condition) failures += 1;
}

function commandAvailable(name) {
  try {
    execFileSync(name, ['--version'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

if (!commandAvailable('python3') || !commandAvailable('git')) {
  console.log('SKIP: el motor exige python3 y git');
  process.exit(3);
}

// ── lógica pura ───────────────────────────────────────────────────────
const cleanDecision = classify({ entries: [
  { path: 'docs/a.md', status: 'CURRENT' },
  { path: 'docs/b.md', status: 'NON_GOVERNING_CHANGE' },
]});
check('classify: veredicto limpio -> repin',
      cleanDecision.action === 'repin'
      && cleanDecision.affectedDocs.length === 0);

const syncDecision = classify({ entries: [
  { path: 'docs/a.md', status: 'CONTRACT_DRIFT', detail: 'changed: x' },
  { path: 'docs/a.md', status: 'SOURCE_DRIFT' },
  { path: 'docs/b.md', status: 'CURRENT' },
]});
check('classify: deriva -> sync, docs únicos y ordenados',
      syncDecision.action === 'sync'
      && JSON.stringify(syncDecision.affectedDocs)
         === JSON.stringify(['docs/a.md']));
check('classify: sin entradas -> close',
      classify({ entries: [] }).action === 'close');
check('writeAllowed: acepta el documento afectado',
      writeAllowed('/repo/docs/a.md', ['docs/a.md']));
check('writeAllowed: rechaza código y prefijos engañosos',
      !writeAllowed('/repo/src/x.py', ['docs/a.md'])
      && !writeAllowed('/repo/docs/a.md.bak', ['docs/a.md']));

// ── repositorio sintético ─────────────────────────────────────────────
const TOOL_V1 = [
  'def public_fn(a: int) -> bool:',
  '    return a > 0',
  '',
  'def other_public() -> str:',
  '    return "stable"',
  '',
].join('\n');
const TOOL_V2 = TOOL_V1.replace(
  'def public_fn(a: int) -> bool:',
  'def public_fn(a: int, b: int) -> bool:');
const API_DOC = [
  '# API',
  '',
  '<!-- drift:track path="src/tool.py" symbols="public_fn" -->',
  '',
  'La firma documentada es la de producción.',
  '',
].join('\n');

const sandbox = mkdtempSync(join(tmpdir(), 'doc-drift-plugin-'));
const repo = join(sandbox, 'product');
const workspace = join(sandbox, 'workspace');
mkdirSync(join(repo, 'src'), { recursive: true });
mkdirSync(join(repo, 'docs'), { recursive: true });
writeFileSync(join(repo, 'src', 'tool.py'), TOOL_V1);
writeFileSync(join(repo, 'docs', 'api.md'), API_DOC);
const git = (...args) =>
  execFileSync('git', ['-C', repo, ...args], { stdio: 'ignore' });
git('init', '-q');
git('add', '-A');
git('-c', 'user.name=Tester', '-c', 'user.email=t@example.test',
    'commit', '-q', '-m', 'base');

function makeCtx() {
  const handlers = new Map();
  const emitted = [];
  return {
    handlers,
    emitted,
    on(name, handler) { handlers.set(name, handler); },
    emit(name, payload) { emitted.push({ name, payload }); },
  };
}

const config = {
  repoRoot: repo,
  workspace,
  enginePath: fileURLToPath(new URL('../drift.py', import.meta.url)),
  python: 'python3',
  targetRev: 'WORKTREE',
};

// ── registro de hooks ─────────────────────────────────────────────────
const ctx = makeCtx();
apply(ctx, config);
for (const hook of ['fs/observed', 'tools/post-execute', 'fs/write-intent',
                    'agent/turn-stopping']) {
  check(`hook registrado: ${hook}`, ctx.handlers.has(hook));
}

const baselinePath = join(workspace, 'drift', 'doc-baseline.json');
const reportPath = join(workspace, 'drift', 'source-drift.json');

// ── turno limpio: re-ancla silenciosa ─────────────────────────────────
let outcome = await ctx.handlers.get('agent/turn-stopping')();
check('cierre limpio: no bloquea', outcome === undefined);
check('cierre limpio: línea base anclada', existsSync(baselinePath));
check('cierre limpio: reporte escrito', existsSync(reportPath));
check('cierre limpio: emite doc-drift/clean con repin',
      ctx.emitted.some((event) => event.name === 'doc-drift/clean'
                       && event.payload.action === 'repin'));
const baselineBefore = JSON.parse(readFileSync(baselinePath, 'utf8'));

// ── deriva de contrato: bloqueo, directiva y confinamiento ────────────
writeFileSync(join(repo, 'src', 'tool.py'), TOOL_V2);
outcome = await ctx.handlers.get('agent/turn-stopping')();
check('deriva: bloquea el cierre',
      outcome?.decision === 'blocked' && outcome?.action === 'sync');
check('deriva: nombra el documento afectado',
      JSON.stringify(outcome?.affectedDocs)
      === JSON.stringify(['docs/api.md']));
const directive = outcome?.additionalContexts?.[0] ?? '';
check('deriva: la directiva lleva estado y documento',
      directive.includes('CONTRACT_DRIFT')
      && directive.includes('docs/api.md'));
check('deriva: emite doc-drift/blocked',
      ctx.emitted.some((event) => event.name === 'doc-drift/blocked'));

const writeIntent = ctx.handlers.get('fs/write-intent');
let denied = false;
try {
  await writeIntent(join(repo, 'src', 'tool.py'), {}, () => undefined);
} catch {
  denied = true;
}
check('confinamiento: escribir código durante el sync se deniega', denied);
const allowed = await writeIntent(join(repo, 'docs', 'api.md'), {}, () => 'ok');
check('confinamiento: el documento afectado se permite', allowed === 'ok');

// ── edición documental: certifica, re-ancla y libera ──────────────────
writeFileSync(join(repo, 'docs', 'api.md'),
              API_DOC + '\nLa firma vigente añade el parámetro `b`.\n');
outcome = await ctx.handlers.get('agent/turn-stopping')();
check('certificación: tras editar el documento no hay bloqueo',
      outcome === undefined);
const baselineAfter = JSON.parse(readFileSync(baselinePath, 'utf8'));
const hashBefore = baselineBefore.documents['docs/api.md'].symbols
  .find((symbol) => symbol.symbol_id === 'src/tool.py::public_fn').contract_hash;
const hashAfter = baselineAfter.documents['docs/api.md'].symbols
  .find((symbol) => symbol.symbol_id === 'src/tool.py::public_fn').contract_hash;
check('certificación: el re-ancla actualizó el contrato',
      hashBefore !== hashAfter);
let released = true;
try {
  await writeIntent(join(repo, 'src', 'tool.py'), {}, () => undefined);
} catch {
  released = false;
}
check('certificación: el confinamiento se libera', released);

// ── fail-closed: motor irresoluble ────────────────────────────────────
const broken = makeCtx();
apply(broken, { ...config, enginePath: join(sandbox, 'missing-engine.py') });
let refused = false;
try {
  await broken.handlers.get('agent/turn-stopping')();
} catch {
  refused = true;
}
check('fail-closed: un motor irresoluble no se lee como limpieza', refused);

console.log(failures
  ? `\n${failures} fallo(s)`
  : '\nOK: verificador de doc-drift en verde');
process.exit(failures ? 1 : 0);
