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

// ── 4. M9: barrido de esquema sobre la tool bash REAL de upstream ────
const registry = new Map();
const guards2 = [];
const realCtx = {
  get(key) {
    if (key === 'sandboxPolicy') return { resolve: () => ({ ...POLICY }) };
    if (key === 'approval') return { request: async () => 'allowed-once' };
    return undefined;
  },
  tools: {
    register: (d) => registry.set(d.name, d),
    guard: (g) => guards2.push(g),
    get: (name) => registry.get(name),
  },
  shell: {
    sandboxMode: 'workspace-write',
    resolve: (r) => r,
    run: async () => ({ exitCode: 0, signal: null, timedOut: false, aborted: false, timeoutMs: 1000, stdout: { text: 'hi', truncated: false }, stderr: { text: '', truncated: false } }),
  },
  shellEnv: { collect: () => ({}) },
  systemPrompt: { section() {}, getSectionOrder() { return 0; } },
};
const realBash = await import(pathToFileURL(process.env.DSH_TOOL_BASH ?? '/home/alan/DSH-workspace/workspaces/Syncify/runtime/dsh-cli/node_modules/@deepseek-ai/dsh-tool-bash/lib/index.js').href);
realBash.apply(realCtx, {});
const before = registry.get('bash');
const hadFields = 'sandbox_permissions' in before.parameters.properties && 'justification' in before.parameters.properties;
check('bash real de upstream registrada CON campos de escalada', hadFields);
check('bash real: descripción original menciona escalada', /escalat|sandbox_permissions/i.test(before.description));

mod.apply(realCtx, {});
const after = registry.get('bash');
check('M9: bash real sin sandbox_permissions en esquema', !('sandbox_permissions' in after.parameters.properties));
check('M9: bash real sin justification en esquema', !('justification' in after.parameters.properties));
check('M9: descripción de bash saneada (sin narrativa de escalada)', !/escalat|sandbox_permissions|justification/i.test(after.description), after.description.slice(0, 80));
check('M9: output schema de bash intacto', after.output.schema.oneOf !== undefined);
check('M9: required de bash preservado', JSON.stringify(after.parameters.required) === JSON.stringify(['command', 'description']), JSON.stringify(after.parameters.required));

const rBash = await after.execute({ command: 'echo hi', description: 'Saluda' }, { signal, agent: undefined });
check('M9: bash real sigue ejecutando tras la mutación', rBash.kind === 'foreground' && rBash.stdout.text === 'hi', JSON.stringify(rBash).slice(0, 120));
check('M9: guard del plugin activo junto a la bash real', guards2.length === 1 && typeof guards2[0](exec('bash', { command: 'ls', description: 'Lista', sandbox_permissions: 'workspace-write', justification: 'x' })) === 'string');

// workflow_write también presente en el mismo registro compartido
check('M9: workflow_write registrada en la composición compartida', registry.get('workflow_write') !== undefined);

// ── 5. M9 vía por-request: waterfall system-prompt/assemble ──────────
let assembleListener;
const realCtx2 = {
  get: realCtx.get,
  tools: { register: (d) => registry.set(d.name, d), guard: (g) => guards2.push(g), get: (name) => registry.get(name) },
  shell: realCtx.shell,
  shellEnv: realCtx.shellEnv,
  systemPrompt: realCtx.systemPrompt,
  on(event, handler) {
    if (event === 'system-prompt/assemble') assembleListener = handler;
    return () => {};
  },
};
const originalBashDescription = 'Execute a bash command. When a command is denied and a wider mode would let it succeed, escalate immediately in the same turn with sandbox_permissions. Do not set sandbox_permissions speculatively.';
const assemblyInput = {
  sections: [],
  contexts: [],
  variables: {},
  tools: [
    { name: 'bash', description: originalBashDescription, parameters: { type: 'object', properties: { command: { type: 'string' }, description: { type: 'string' }, sandbox_permissions: { type: 'string', enum: ['workspace-write'] }, justification: { type: 'string' } }, required: ['command', 'description'] } },
    { name: 'read', description: 'Read a file.', parameters: { type: 'object', properties: { file_path: { type: 'string' } }, required: ['file_path'] } },
  ],
};
mod.apply(realCtx2, {});
check('M9: plugin registra listener de system-prompt/assemble', typeof assembleListener === 'function');
const assembled = await assembleListener(assemblyInput, {}, async () => assemblyInput);
const bashWire = assembled.tools.find((t) => t.name === 'bash');
const readWire = assembled.tools.find((t) => t.name === 'read');
check('M9 waterfall: bash sin sandbox_permissions', bashWire && !('sandbox_permissions' in bashWire.parameters.properties));
check('M9 waterfall: bash sin justification', bashWire && !('justification' in bashWire.parameters.properties));
check('M9 waterfall: required sin campos de escalada', JSON.stringify(bashWire.parameters.required) === JSON.stringify(['command', 'description']), JSON.stringify(bashWire.parameters.required));
check('M9 waterfall: descripción de bash saneada', !/escalat|sandbox_permissions|justification/i.test(bashWire.description), bashWire.description);
check('M9 waterfall: read NO alterada', readWire === assemblyInput.tools[1]);
check('M9 waterfall: input original no mutado', 'sandbox_permissions' in assemblyInput.tools[0].parameters.properties);
const passInput = { tools: [{ name: 'x', parameters: { type: 'object', properties: { a: { type: 'string' } } } }] };
const passthrough = await assembleListener(passInput, {}, async () => passInput);
check('M9 waterfall: tools sin campos pasan intactas', passthrough.tools[0] === passInput.tools[0]);

console.log(failures === 0 ? '\nTODO OK' : `\n${failures} FALLOS`);
process.exit(failures === 0 ? 0 : 1);
