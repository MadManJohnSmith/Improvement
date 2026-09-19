import { pathToFileURL } from 'node:url';

// Portable: el plugin se resuelve junto a este script; la ruta del runtime se
// puede invalidar con DSH_TOOLS_INDEX (…/dsh-cli/node_modules/@deepseek-ai/dsh-tools/lib/index.js).
const TOOLS = process.env.DSH_TOOLS_INDEX ?? '/home/alan/DSH-workspace/workspaces/Syncify/runtime/dsh-cli/node_modules/@deepseek-ai/dsh-tools/lib/index.js';
const PLUGIN = new URL('./workflow-write.mjs', import.meta.url).href;
const { assertSupportedJsonSchema, validateJsonSchemaValue, jsonSchemaToTs } = await import(pathToFileURL(TOOLS).href);

let failures = 0;
function check(label, cond, detail = '') {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? `  -> ${detail}` : ''}`);
  if (!cond) failures++;
}

// ── mock ctx ──────────────────────────────────────────────────────────
const registered = [];
const guards = [];
const calls = {};
const POLICY = { mode: 'workspace-write', workspaceRoot: '/ws/root' };
const ctx = {
  get(key) {
    if (key === 'sandboxPolicy') return { resolve: () => ({ ...POLICY }) };
    if (key === 'approval') { calls.approval = (calls.approval ?? 0) + 1; return { request: async () => 'allowed-once' }; }
    return undefined;
  },
  tools: { register: (d) => registered.push(d), guard: (g) => guards.push(g) },
  fs: {
    resolve: async (p, opts) => { calls.resolve = { p, opts }; return { displayPath: `/abs/${p}` }; },
    writeText: async (t, c, intent, signal, policy) => {
      calls.writeText = { t, c, policyMode: policy?.mode };
      return { version: 3, operation: 'create', before: null, after: c };
    },
  },
  waterfall: async (name, _t, _e, fb) => { calls.waterfall = name; return fb(); },
  emit: () => {},
};

const mod = await import(PLUGIN);
mod.apply(ctx, {});

const wf = registered.find((d) => d.name === 'workflow_write');
check('workflow_write registrada', wf !== undefined);

// ── 1. esquema publicado ─────────────────────────────────────────────
try {
  assertSupportedJsonSchema(wf.parameters);
  check('parameters: JSON Schema soportado por el runtime', true);
} catch (e) {
  check('parameters: JSON Schema soportado por el runtime', false, e.message);
}
const sig = jsonSchemaToTs(wf.parameters, 1);
check('firma model-facing NO degenerada (no any/unknown)', !/\bany\b|\bunknown\b/.test(sig), sig.replace(/\n/g, ' '));

const vOk = validateJsonSchemaValue(wf.parameters, { file_path: 'a.txt', content: 'hola' }, '');
check('args válidos pasan validación', vOk.length === 0, JSON.stringify(vOk));
const vEmpty = validateJsonSchemaValue(wf.parameters, {}, '');
check('args vacíos ({}) RECHAZADOS (required efectivo)', vEmpty.length > 0, JSON.stringify(vEmpty));
const vNoContent = validateJsonSchemaValue(wf.parameters, { file_path: 'a.txt' }, '');
check('falta content -> rechazado', vNoContent.length > 0, JSON.stringify(vNoContent));

// reproducción del defecto M8: mapa de propiedades (versión anterior)
const oldParams = {
  file_path: { type: 'string', required: true, description: 'x' },
  content: { type: 'string', required: true, description: 'x' },
};
let oldSig;
try { oldSig = jsonSchemaToTs(oldParams, 1); } catch (e) { oldSig = `(throw) ${e.message}`; }
const oldValidate = validateJsonSchemaValue(oldParams, {}, '');
console.log(`INFO  defecto M8 reproducido: firma con mapa de propiedades = ${JSON.stringify(oldSig)}; validación de {} = ${JSON.stringify(oldValidate)}`);

// ── 2. guard ─────────────────────────────────────────────────────────
check('guard registrado', guards.length === 1);
const guard = guards[0];
const exec = (name, args) => ({ name, arguments: args, agent: undefined });

const gSame = guard(exec('bash', { command: 'ls', description: 'Lista', sandbox_permissions: 'workspace-write', justification: 'necesito escribir' }));
check('bash + mismo modo -> denegado con mensaje correctivo', typeof gSame === 'string' && gSame.includes('no es una escalada'), String(gSame).slice(0, 90));

const gJust = guard(exec('bash', { command: 'ls', description: 'Lista', justification: 'x' }));
check('bash + justification a secas -> denegado', typeof gJust === 'string');

const gNoJust = guard(exec('bash', { command: 'ls', description: 'Lista', sandbox_permissions: 'workspace-write' }));
check('bash + sandbox_permissions sin justification -> denegado', typeof gNoJust === 'string');

const gNarrow = guard(exec('bash', { command: 'ls', description: 'Lista', sandbox_permissions: 'workspace-write', justification: 'x' }));
check('(sanidad) misma combinación evaluada contra policy workspace-write', typeof gNarrow === 'string');

const gWider = guard(exec('bash', { command: 'ls', description: 'Lista', sandbox_permissions: 'danger-full-access', justification: 'x' }));
check('bash + modo estrictamente mayor -> pasa a aprobación de upstream', gWider === undefined);

const gClean = guard(exec('bash', { command: 'ls', description: 'Lista' }));
check('bash limpio -> no denegado', gClean === undefined);

const gWf = guard(exec('workflow_write', { file_path: 'a', content: 'b', sandbox_permissions: 'workspace-write' }));
check('workflow_write no afectada por el guard', gWf === undefined);

// ── 3. execute ───────────────────────────────────────────────────────
const signal = new AbortController().signal;
const r = await wf.execute({ file_path: 'out/x.txt', content: 'hola' }, { signal });
check('execute devuelve resultado canónico', r.path === '/abs/out/x.txt' && r.operation === 'create' && r.after === 'hola', JSON.stringify(r));
check('resolve recibió opciones de sesión (cwd de la política + signal)', calls.resolve.opts.cwd === '/ws/root' && calls.resolve.opts.signal === signal, JSON.stringify(calls.resolve.opts));
check('writeText recibió la política resuelta', calls.writeText.policyMode === 'workspace-write');
check('waterfall fs/write-intent invocado', calls.waterfall === 'fs/write-intent');
check('sin escalada no se toca approval', calls.approval === undefined);

// M7: mismo modo via parámetros forzados -> no-op, sin approval
calls.approval = undefined;
await wf.execute({ file_path: 'a', content: 'b', sandbox_permissions: 'workspace-write', justification: 'x' }, { signal });
check('M7: sandbox_permissions == modo vigente -> no-op sin approval', calls.approval === undefined);

// M7: escalada estrictamente mayor -> approval real
await wf.execute({ file_path: 'a', content: 'b', sandbox_permissions: 'danger-full-access', justification: 'x' }, { signal });
check('M7: escalada estrictamente mayor -> approval invocado', calls.approval === 1);

// args defectuosos
const e1 = await wf.execute({}, { signal }).catch((e) => e.message);
check('sin args -> file_path debe ser un string no vacío', e1 === 'file_path debe ser un string no vacío', e1);

console.log(failures === 0 ? '\nTODO OK' : `\n${failures} FALLOS`);
process.exit(failures === 0 ? 0 : 1);
