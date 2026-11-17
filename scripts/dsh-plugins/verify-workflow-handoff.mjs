/**
 * verify-workflow-handoff: regresión offline del gate de handoffs del plugin
 * workflow-write (issue #38).
 *
 * Sin runtime DSH: un ctx simulado invoca la tool REAL `workflow_write` del
 * plugin (`apply`) contra un mode-state de fixture en un directorio temporal.
 * Cubre la lógica determinista que retuvo toda campaña sobre la misma base:
 *
 *   - el next_prompt aterrizado de un handoff de auditoría es siempre el del
 *     contrato (normalización en el write; el derivado «no públicas» ya no
 *     puede aterrizar con el id de la convención);
 *   - un handoff nuevo sobre una base con handoff previo aterriza (cada
 *     auditoría real merece su registro);
 *   - el dedup es visible: un handoff_id aterrizado se re-emite solo con la
 *     misma base y finding_ids; con otros se refusa citable;
 *   - la re-emisión exacta cura un registro histórico derivado por la ruta
 *     soportada (el write), nunca a mano;
 *   - la cobertura exacta de los OPEN de la base y el schema estricto siguen
 *     refusando;
 *   - un ledger aterrizado ilegible refusa el write en vez de adivinar el dedup.
 *
 * Requiere node. Sin él sale 3 (skip declarado), nunca 0.
 */
import { mkdtempSync, readFileSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve as presolve } from 'node:path';

import { apply, validateManagedHandoff } from './workflow-write.mjs';

let failures = 0;
function check(label, condition, detail = '') {
  console.log(`${condition ? 'PASS' : 'FAIL'}  ${label}${detail ? `  -> ${detail}` : ''}`);
  if (!condition) failures += 1;
}

const BASE = 'b40829ad18a61a31042a5e3bcfeb0125828f8e21';
const OTHER_BASE = 'a'.repeat(40);
const CONTRACT = 'Repara los hallazgos de la auditoría; no publiques.';
const DERIVED = 'Repara los hallazgos de la auditoría; no públicas.';

const FINDINGS = [
  { finding_id: 'A-05', base_revision: BASE, severity: 'HIGH', status: 'OPEN', summary: 'Prevention failed for A-04' },
  { finding_id: 'A-01', base_revision: BASE, severity: 'HIGH', status: 'RESOLVED', summary: 'old defect' },
  { finding_id: 'A-06', base_revision: OTHER_BASE, severity: 'MEDIUM', status: 'OPEN', summary: 'other base' },
].map((record) => JSON.stringify(record)).join('\n') + '\n';
const HANDOFF_6 = JSON.stringify({
  handoff_id: 'audit-complete-b40829ad-6', base_revision: BASE,
  finding_ids: ['A-05'], next_prompt: DERIVED,
}) + '\n';

function fixture({ ledger = HANDOFF_6, findings = FINDINGS } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'verify-handoff-'));
  const state = join(root, 'mode-state');
  mkdirSync(state);
  if (ledger !== null) writeFileSync(join(state, 'handoffs.jsonl'), ledger);
  if (findings !== null) writeFileSync(join(state, 'findings.jsonl'), findings);
  return root;
}

function buildCtx(root) {
  const written = [];
  const ctx = {
    get: (name) => (name === 'sandboxPolicy'
      ? { resolve: () => ({ mode: 'workspace-write' }) } : undefined),
    emit: () => {},
    waterfall: async () => ({}),
    tools: { register: (def) => { ctx.captured = def; }, guard: () => {}, get: () => undefined },
    fs: {
      async processPath(target) { return target.displayPath; },
      async resolve(p, { cwd }) {
        return { targetKey: presolve(cwd, p), displayPath: presolve(cwd, p) };
      },
      async stat(target) {
        try { return readFileSync(target.targetKey); } catch { return null; }
      },
      async readText(target) {
        return readFileSync(target.targetKey, 'utf8');
      },
      async writeText(target, content) {
        writeFileSync(target.targetKey, content);
        written.push({ path: target.targetKey, content });
        return { version: 1, operation: 'update', before: null, after: content };
      },
    },
  };
  apply(ctx, {});
  return { ctx, written };
}

async function executeWrite(root, ctx, content) {
  return ctx.captured.execute(
    { file_path: join(root, 'mode-state', 'handoffs.jsonl'), content },
    { agent: { session: { header: { cwd: root } } }, callId: 'verify', signal: undefined });
}

function landed(root) {
  return readFileSync(join(root, 'mode-state', 'handoffs.jsonl'), 'utf8')
    .trim().split('\n').filter((line) => line !== '')
    .map((line) => JSON.parse(line));
}

const handoff7 = (prompt = CONTRACT, ids = ['A-05'], base = BASE) => JSON.stringify({
  handoff_id: 'audit-complete-b40829ad-7', base_revision: base,
  finding_ids: ids, next_prompt: prompt,
}) + '\n';

// ── el next_prompt aterrizado es siempre el del contrato ──────────────
{
  const root = fixture();
  const { ctx, written } = buildCtx(root);
  await executeWrite(root, ctx, handoff7(DERIVED));
  const disk = landed(root);
  check('un handoff de auditoría derivado aterriza normalizado al contrato',
        disk.length === 1 && disk[0].next_prompt === CONTRACT
        && disk[0].handoff_id === 'audit-complete-b40829ad-7',
        JSON.stringify(disk));
  check('el write ejecutado es el que aterriza (no solo la validación)',
        written.length === 1 && written[0].content.includes(CONTRACT));
  rmSync(root, { recursive: true, force: true });
}

// ── handoff de reparación: prompt propio y cobertura parcial ──────────
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  await executeWrite(root, ctx, JSON.stringify({
    handoff_id: 'repair-toma-1', base_revision: BASE,
    finding_ids: ['A-01'], next_prompt: 'Repara A-01; no publiques.',
  }) + '\n');
  const disk = landed(root);
  check('un handoff de reparación (fuera de la convención de auditoría) '
        + 'conserva su prompt propio y su cobertura parcial',
        disk.length === 1 && disk[0].handoff_id === 'repair-toma-1'
        && disk[0].next_prompt === 'Repara A-01; no publiques.'
        && JSON.stringify(disk[0].finding_ids) === '["A-01"]');
  rmSync(root, { recursive: true, force: true });
}

// ── handoff nuevo sobre base con handoff previo: aterriza ─────────────
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  await executeWrite(root, ctx, handoff7());
  const disk = landed(root);
  check('un handoff nuevo sobre una base con handoff previo aterriza',
        disk.length === 1 && disk[0].handoff_id === 'audit-complete-b40829ad-7'
        && disk[0].next_prompt === CONTRACT);
  rmSync(root, { recursive: true, force: true });
}

// ── dedup visible: re-emisión exacta cura; reescritura refusa ─────────
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  await executeWrite(root, ctx, HANDOFF_6);
  const disk = landed(root);
  check('la re-emisión exacta del -6 derivado cura el registro por la ruta soportada',
        disk.length === 1 && disk[0].handoff_id === 'audit-complete-b40829ad-6'
        && disk[0].next_prompt === CONTRACT);
  rmSync(root, { recursive: true, force: true });
}
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  let refusal = null;
  try {
    await executeWrite(root, ctx, JSON.stringify({
      handoff_id: 'audit-complete-b40829ad-6', base_revision: BASE,
      finding_ids: ['A-01', 'A-05'], next_prompt: CONTRACT,
    }) + '\n');
  } catch (error) { refusal = error.message; }
  check('un handoff_id aterrizado con otras finding_ids se refusa citable',
        refusal !== null && refusal.includes('reescribe el handoff aterrizado')
        && refusal.includes('audit-complete-b40829ad-6'), refusal);
  rmSync(root, { recursive: true, force: true });
}
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  let refusal = null;
  try {
    await executeWrite(root, ctx, JSON.stringify({
      handoff_id: 'audit-complete-b40829ad-6', base_revision: OTHER_BASE,
      finding_ids: ['A-06'], next_prompt: CONTRACT,
    }) + '\n');
  } catch (error) { refusal = error.message; }
  check('un handoff_id aterrizado con otra base se refusa citable',
        refusal !== null && refusal.includes('reescribe el handoff aterrizado'), refusal);
  rmSync(root, { recursive: true, force: true });
}
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  await executeWrite(root, ctx, HANDOFF_6.trim() + '\n' + handoff7());
  const disk = landed(root);
  check('el eco del histórico más el handoff nuevo aterriza todo contrato-exacto',
        disk.length === 2 && disk.every((record) => record.next_prompt === CONTRACT)
        && disk.map((record) => record.handoff_id).join(',')
           === 'audit-complete-b40829ad-6,audit-complete-b40829ad-7');
  rmSync(root, { recursive: true, force: true });
}

// ── cobertura y schema siguen refusando ───────────────────────────────
{
  const root = fixture();
  const { ctx } = buildCtx(root);
  const attempts = [
    ['nombra un hallazgo no persistido', handoff7(CONTRACT, ['A-09'])],
    ['omite el OPEN de la base', handoff7(CONTRACT, ['A-01'])],
    ['nombra un no OPEN', handoff7(CONTRACT, ['A-05', 'A-01'])],
    ['schema: base no hex', handoff7(CONTRACT, ['A-05'], 'no-hex')],
    ['schema: next_prompt vacío', handoff7('')],
  ];
  for (const [label, content] of attempts) {
    let refusal = null;
    try { await executeWrite(root, ctx, content); }
    catch (error) { refusal = error.message; }
    check(`refusa citable: ${label}`, refusal !== null, refusal ?? 'aterrizó');
  }
  rmSync(root, { recursive: true, force: true });
}

// ── ledger ilegible: refuse, never guess the dedup ────────────────────
{
  const root = fixture({ ledger: 'no-es-json\n' });
  const { ctx } = buildCtx(root);
  let refusal = null;
  try { await executeWrite(root, ctx, handoff7()); }
  catch (error) { refusal = error.message; }
  check('un ledger aterrizado ilegible refusa el write',
        refusal !== null && refusal.includes('handoffs.jsonl aterrizado'), refusal);
  rmSync(root, { recursive: true, force: true });
}

// ── primera escritura sin ledger y destino ajeno ──────────────────────
{
  const root = fixture({ ledger: null });
  const { ctx } = buildCtx(root);
  await executeWrite(root, ctx, handoff7());
  const disk = landed(root);
  check('la primera escritura (sin ledger) aterriza',
        disk.length === 1 && disk[0].next_prompt === CONTRACT);
  rmSync(root, { recursive: true, force: true });
}
{
  const root = fixture();
  const { ctx, written } = buildCtx(root);
  await ctx.captured.execute(
    { file_path: join(root, 'otro.txt'), content: 'passthrough' },
    { agent: { session: { header: { cwd: root } } }, callId: 'verify', signal: undefined });
  check('un destino que no es handoffs pasa sin normalizar',
        written.length === 1 && written[0].content === 'passthrough');
  rmSync(root, { recursive: true, force: true });
}

// ── validateManagedHandoff exportada: contrato de la firma ────────────
{
  check('validateManagedHandoff es exportada para el verificador offline',
        typeof validateManagedHandoff === 'function');
}

if (failures > 0) {
  console.log(`FAIL: ${failures} comprobaciones en rojo`);
  process.exit(1);
}
console.log('OK: verificador de handoffs de auditoría en verde');
