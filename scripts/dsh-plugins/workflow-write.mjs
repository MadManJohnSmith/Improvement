/**
 * workflow-write: herramienta de escritura con semántica de escalada corregida.
 *
 * Defecto M7 (2026-09-13): `write`/`bash` de upstream rechazan «sandbox
 * escalation ... is not strictly wider» cuando el modelo envía
 * sandbox_permissions igual al modo ya vigente, bloqueando escrituras y comandos.
 *
 * Defecto M8 (2026-09-19): este plugin pasaba a ctx.tools.register() un mapa de
 * propiedades, pero register() NO compila parámetros (eso lo hace defineTool());
 * el esquema publicado salía degenerado, el modelo veía la firma
 * `workflow_write = () => any`, llamaba sin argumentos y execute fallaba en
 * bucle con «file_path debe ser un string no vacío».
 *
 * Defecto M9 (2026-09-19, sesión tardis): el modelo envía sandbox_permissions
 * en TODA llamada bash desde la primera (sin denegación previa) pese a tres
 * capas de instrucción contraria (prompt de misión, contexto de runtime y
 * mensaje correctivo del guard M7); 60+ llamadas idénticas quemaron la sesión
 * delegada. La cura es estructural: retirar los campos del esquema
 * model-facing. Se aplican dos vías:
 *  1. Waterfall system-prompt/assemble (por request, la efectiva): el
 *     assembly re-deriva las schemas de las definiciones en cada paso
 *     (structuredClone vía wireSchemas) y su valor transformado es
 *     autoritario; assembly.tools es exactamente el array de
 *     function-calling. El hook sanea cada tool (parámetros y descripción)
 *     para todos los agentes y subagentes, sin importar cuándo se
 *     registraron las filas de tool de los presets (por sesión, no en boot).
 *  2. Barrido en apply de las definiciones ya registradas (bash/pwsh/write/
 *     edit): cubre composiciones donde las tools existen en boot. La
 *     ejecución aguanta igual: los validadores de args de defineTool solo
 *     miran claves anunciadas, y el guard sigue denegando cualquier
 *     aparición residual antes del dispatch.
 *
 * Correcciones de este plugin (mantenedor, no Creator):
 *  1. workflow_write registra un JSON Schema CRUDO ya compilado
 *     ({type:'object', properties, required}), la forma que register() consume.
 *  2. resolvePolicy corrige M7 para workflow_write: mismo modo -> política
 *     vigente (no es escalada); estrictamente mayor -> aprobación fail-closed
 *     del servicio `approval`; más estrecho -> política vigente.
 *  3. Guard global en tools/pre-execute: si bash/pwsh llegan con
 *     sandbox_permissions/justification, se deniegan todos los valores ANTES
 *     del dispatch o la aprobación y sin sugerir reintento, cortando los bucles
 *     observados el 2026-09-19 y 2026-09-27.
 *  4. execute replica la tool write de upstream: ctx.fs.resolve con opciones de
 *     sesión (cwd = raíz de la política o cwd de la sesión, señal de aborto),
 *     waterfall fs/write-intent, writeText con la política resuelta y emisión
 *  5. G7: antes de reemplazar el verification-results.jsonl gestionado, resuelve
 *     canónicamente su capability-plan.json hermano y rechaza cualquier comando
 *     que no sea un entrypoint real ligado al plan o PASS/FAIL sin capacidad.
 *     fs/observed. Los parámetros de escalada NO se publican en el esquema
 *     (las misiones prohíben enviarlos); quedan cubiertos por resolvePolicy si
 *     un modelo los fuerza.
 *  6. Confinamiento de la escritura de estado: una sesión gestionada (un hijo
 *     inmediato del cwd marcado por el capability-plan del Host) declara su raíz
 *     `<workspace>/mode-state`, y todo destino resuelto fuera de ella se deniega
 *     antes del write-intent. La frontera de solo lectura del auditor la impone
 *     así la herramienta y no el Git posterior. Una sesión sin workspace
 *     gestionado conserva el comportamiento anterior: el revisor de aceptación
 *     sigue escribiendo su result.json.
 *
 * Sin aprobación, falla cerrado; el aislamiento no se debilita: la ejecución
 * siempre pasa por ctx.fs.writeText con la política resuelta, igual que upstream.
 */
import { createHash } from 'node:crypto';

export const inject = ['tools', 'fs', 'systemPrompt'];

const MANAGED_RESULTS_SUFFIX = '/mode-state/verification-results.jsonl';
const MANAGED_HANDOFFS_SUFFIX = '/mode-state/handoffs.jsonl';
const MANAGED_FINDINGS_SUFFIX = '/mode-state/findings.jsonl';
const PLAN_RELATIVE = '.dsh-managed/capability-plan.json';
const PLAN_BYTE_LIMIT = 131072;
const FINDINGS_BYTE_LIMIT = 262144;
const ANCHORED_FILE_BYTE_LIMIT = 1048576;
const ANCHOR_EXCERPT_MIN = 8;
const STATE_DIR_NAME = 'mode-state';
const LEASE_DIR_NAME = '.leases';
const LEASE_TTL_MS = 30000;
const EVIDENCE_DIR_NAME = 'evidence';
const EVIDENCE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/u;
const EVIDENCE_FILE_LIMIT = 200;
const EVIDENCE_TOTAL_BYTES = 268435456;
const EVIDENCE_FILE_BYTES = 8388608;
const AUDIT_NEXT_PROMPT = 'Repara los hallazgos de la auditoría; no publiques.';
const REVISION = /^[0-9a-f]{40,64}$/u;
const FINDING_FIELDS = ['base_revision', 'cause', 'finding_id', 'prevention', 'severity', 'status', 'summary'];
const RECORD_BYTE_LIMIT = 4096;
const CAUSE_MAX_BYTES = 256;
const PREVENTION_MAX_BYTES = 256;
const SEVERITIES = ['CRITICAL', 'HIGH', 'LOW', 'MEDIUM'];
const STATUSES = ['OPEN', 'RESOLVED', 'RETAINED'];
const TRAVERSAL = /(?:^|\/)\.\.(?:\/|$)/u;

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function asPosixPath(value) {
  return typeof value === 'string' ? value.replace(/\\/g, '/').replace(/\/+$/, '') : '';
}

/**
 * State root the session is bound to, or null when it is not a managed one.
 *
 * The mode contract confines state writes to `<workspace>/mode-state`, where
 * the workspace is an immediate child of the session cwd that the Host marked
 * as managed with its capability plan. Deriving the root from the session, not
 * from the target, is the point: anchoring on the target only proves the
 * destination is shaped like state, and a product path shaped like anything
 * else would pass.
 */
async function managedStateRoot(ctx, cwd, signal) {
  if (typeof cwd !== 'string' || cwd === '') return null;
  if (typeof ctx.fs.listDir !== 'function' || typeof ctx.fs.processPath !== 'function'
      || typeof ctx.fs.resolve !== 'function' || typeof ctx.fs.stat !== 'function') return null;
  const sessionRoot = asPosixPath(cwd);
  let entries;
  try {
    entries = await ctx.fs.listDir(await ctx.fs.resolve('.', {cwd, signal}), signal);
  } catch {
    return null;
  }
  const workspaces = [];
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (entry?.type !== 'directory') continue;
    const child = asPosixPath(ctx.fs.processPath(entry.target));
    if (child === '' || !child.startsWith(`${sessionRoot}/`)) continue;
    let plan;
    try {
      plan = await ctx.fs.stat(
        await ctx.fs.resolve(PLAN_RELATIVE, {cwd: child, signal}), signal);
    } catch {
      continue;
    }
    if (plan?.type === 'file') workspaces.push(child);
  }
  if (workspaces.length === 0) return null;
  if (workspaces.length > 1) {
    throw new Error('workflow_write: la sesión declara más de un workspace gestionado; '
      + `${workspaces.join(', ')}; denegado sin reintento`);
  }
  return `${workspaces[0]}/${STATE_DIR_NAME}`;
}

async function assertStateWrite(ctx, target, stateRoot, evidenceRoot, content) {
  if (typeof ctx.fs.processPath !== 'function') return;
  const resolved = ctx.fs.processPath(target);
  if (typeof resolved !== 'string') return;
  // processPath keeps the physical spelling, so a `..` segment survives
  // resolution. It is refused instead of normalized: the canonical tree is
  // the only tree a state write may touch.
  if (TRAVERSAL.test(resolved.replace(/\\/g, '/'))) {
    throw new Error('workflow_write: ruta de escritura de estado no canónica; denegado sin reintento');
  }
  const candidate = asPosixPath(resolved);
  const inState = candidate === stateRoot || candidate.startsWith(`${stateRoot}/`);
  const inEvidence = evidenceRoot
    && (candidate === evidenceRoot || candidate.startsWith(`${evidenceRoot}/`));
  if (!inState && !inEvidence) {
    throw new Error(`workflow_write: la escritura de estado sale de ${stateRoot}: ${candidate}; `
      + 'denegado sin reintento');
  }
  if (inEvidence) await assertEvidenceBudget(ctx, candidate, evidenceRoot, content);
}

/**
 * Evidence that outgrows a 4 KiB record is still evidence, so it has a managed
 * home with its own caps instead of being written into the state root, where
 * the preflight would archive it as a stray file. The caps are checked before
 * the write, not after: an artifact the budget cannot hold is refused with a
 * reason the persona can receipt, never silently dropped.
 */
async function assertEvidenceBudget(ctx, candidate, evidenceRoot, content) {
  const name = candidate.slice(evidenceRoot.length + 1);
  if (!EVIDENCE_NAME.test(name)) {
    throw new Error(`workflow_write: nombre de evidencia no seguro: ${name}`);
  }
  const size = Buffer.byteLength(typeof content === 'string' ? content : '', 'utf8');
  if (size > EVIDENCE_FILE_BYTES) {
    throw new Error(`workflow_write: el artefacto ocupa ${size} bytes y el tope por fichero es `
      + `${EVIDENCE_FILE_BYTES}; resume la evidencia en el estado y guarda solo lo imprescindible`);
  }
  const entries = await ctx.fs.listDir(await ctx.fs.resolve('.', {cwd: evidenceRoot})).catch(() => []);
  let total = 0;
  let count = 0;
  for (const entry of entries) {
    if (entry?.type !== 'file') continue;
    const other = asPosixPath(ctx.fs.processPath(entry.target));
    if (other === candidate) continue;
    const info = await ctx.fs.stat(entry.target).catch(() => undefined);
    total += typeof info?.size === 'number' ? info.size : 0;
    count += 1;
  }
  if (count + 1 > EVIDENCE_FILE_LIMIT) {
    throw new Error(`workflow_write: la raíz de evidencia ya tiene ${count} ficheros `
      + `(tope ${EVIDENCE_FILE_LIMIT}); registra el descarte en overflows.jsonl y retira lo obsoleto`);
  }
  if (total > EVIDENCE_TOTAL_BYTES - EVIDENCE_FILE_BYTES) {
    throw new Error(`workflow_write: la raíz de evidencia ya ocupa ${total} bytes `
      + `(tope ${EVIDENCE_TOTAL_BYTES}); registra el descarte en overflows.jsonl y retira lo obsoleto`);
  }
}

/**
 * The signed capability plan, or nothing. Shared by every managed gate so the
 * product root and the entrypoints come from the same Host-signed input.
 */
async function loadSignedPlan(ctx, workspacePath, signal) {
  const planTarget = await ctx.fs.resolve(PLAN_RELATIVE, { cwd: workspacePath, signal });
  const planText = await ctx.fs.readText(planTarget, signal);
  if (typeof planText !== 'string' || Buffer.byteLength(planText, 'utf8') > PLAN_BYTE_LIMIT) {
    throw new Error('capability-plan ausente o excesivo');
  }
  let plan;
  try { plan = JSON.parse(planText); } catch { throw new Error('capability-plan inválido'); }
  if (!plan || plan.version !== 1 || !Array.isArray(plan.stacks)) {
    throw new Error('capability-plan inválido');
  }
  const { plan_sha256: recordedDigest, ...unsignedPlan } = plan;
  const actualDigest = createHash('sha256').update(canonicalJson(unsignedPlan), 'utf8').digest('hex');
  if (typeof recordedDigest !== 'string' || recordedDigest !== actualDigest) {
    throw new Error('capability-plan alterado');
  }
  return plan;
}

function planCommands(plan) {
  const commands = new Map();
  for (const stack of plan.stacks) {
    const ready = stack?.verification_ready === true;
    for (const command of [stack?.verify_command, stack?.lint_command]) {
      if (!Array.isArray(command) || command.length === 0 || command.some((part) => typeof part !== 'string')) continue;
      const key = canonicalJson(command);
      // If two stacks share one command, the strictest readiness wins.
      commands.set(key, commands.has(key) ? commands.get(key) && ready : ready);
    }
  }
  return commands;
}

async function validateManagedVerification(ctx, target, content, signal) {
  if (typeof ctx.fs.processPath !== 'function') return;
  const rawTargetPath = await ctx.fs.processPath(target);
  if (typeof rawTargetPath !== 'string') return;
  const targetPath = rawTargetPath.replace(/\\/g, '/').replace(/\/+$/, '');
  if (!targetPath.endsWith(MANAGED_RESULTS_SUFFIX)) return;

  const workspacePath = targetPath.slice(0, -MANAGED_RESULTS_SUFFIX.length);
  const expectedTarget = await ctx.fs.resolve('mode-state/verification-results.jsonl', {
    cwd: workspacePath, signal,
  });
  if (!expectedTarget || expectedTarget.targetKey !== target.targetKey) {
    throw new Error('verification-results target no coincide con el mode-state gestionado');
  }
  const plan = await loadSignedPlan(ctx, workspacePath, signal);
  const commands = planCommands(plan);
  const lines = content.endsWith('\n') ? content.slice(0, -1).split('\n') : content.split('\n');
  if (lines.length === 1 && lines[0] === '') return;
  if (lines.some((line) => line.trim() === '')) throw new Error('verification-results contiene línea vacía');
  for (let index = 0; index < lines.length; index++) {
    let record;
    try { record = JSON.parse(lines[index]); } catch { throw new Error(`verification-result ${index} inválido`); }
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error(`verification-result ${index} inválido`);
    }
    const keys = Object.keys(record).sort();
    const required = ['candidate_diff_digest', 'candidate_head', 'command', 'finding_id', 'result'];
    if (keys.length !== required.length || keys.some((key, offset) => key !== required[offset])
        || typeof record.finding_id !== 'string' || record.finding_id.length === 0
        || typeof record.candidate_head !== 'string'
        || !/^[0-9a-f]{40,64}$/.test(record.candidate_head)
        || typeof record.candidate_diff_digest !== 'string'
        || !/^[0-9a-f]{64}$/.test(record.candidate_diff_digest)) {
      throw new Error(`verification-result ${index} no cumple el schema estricto`);
    }
    if (!commands.has(record.command)) {
      throw new Error(`verification-result ${index} usa comando ajeno al stack real`);
    }
    if (!['PASS', 'FAIL', 'BLOCKED'].includes(record.result)) {
      throw new Error(`verification-result ${index} tiene resultado inválido`);
    }
    if (commands.get(record.command) !== true && record.result !== 'BLOCKED') {
      throw new Error(`verification-result ${index} debe ser BLOCKED: falta capacidad del stack`);
    }
  }
  // One record says what one entrypoint said. PASS and BLOCKED coexist for a
  // finding — that is a partial result and the Host derives it — but PASS
  // against FAIL on the same tree is a contradiction no rule could resolve
  // afterwards, so it never reaches the state.
  const decided = new Map();
  lines.forEach((line, index) => {
    const record = JSON.parse(line);
    if (record.result === 'BLOCKED') return;
    const key = `${record.finding_id}@${record.candidate_head}`;
    if (decided.has(key) && decided.get(key) !== record.result) {
      throw new Error(`verification-result ${index} contradice el veredicto de otro registro del mismo hallazgo`);
    }
    decided.set(key, record.result);
  });
}

function targetPathUnder(root, target) {
  if (typeof target?.targetKey !== 'string') return null;
  const candidate = asPosixPath(target.targetKey);
  if (!candidate.startsWith(`${root}/`)) return null;
  const relative = candidate.slice(root.length + 1);
  return relative.length > 0 && !relative.includes('/') ? relative : null;
}

/**
 * A per-file lease, so two sessions cannot interleave a replacement of the
 * same state file.
 *
 * `write_method` is already declared non-atomic across files, and nothing the
 * filesystem backend offers can make a five-file replacement one transaction.
 * What it *can* stop is the narrower and more common failure: one session
 * reading a half-written file while another replaces it, or the last writer
 * silently discarding a write it never saw. The lease is taken before
 * writeText and released after it, and an expired lease may be taken over, so
 * a session that dies holding one cannot wedge the state forever.
 */
function leaseIdentity(exec) {
  const session = exec?.agent?.session;
  const id = session?.id || session?.sessionId || session?.header?.sessionId;
  return typeof id === 'string' && id.length > 0 ? id : null;
}

async function acquireLease(ctx, stateRoot, relative, session, now, policy) {
  const leaseDir = `${stateRoot}/${LEASE_DIR_NAME}`;
  const leasePath = `${leaseDir}/${relative}.json`;
  const target = await ctx.fs.resolve(`${LEASE_DIR_NAME}/${relative}.json`, {
    cwd: `${stateRoot}/`, signal: undefined,
  }).catch(() => null);
  if (!target) return null;
  let held = null;
  try {
    held = JSON.parse(await ctx.fs.readText(target));
  } catch {
    held = null;
  }
  if (held && held.state === 'held' && held.session !== session
      && typeof held.expires_at === 'number' && held.expires_at > now) {
    throw new Error(`workflow_write: ${relative} está siendo escrito por otra sesión `
      + `(arrendada ${Math.max(0, Math.round((now - held.acquired_at) / 1000))} s atrás); `
      + 'denegado sin reintento');
  }
  const lease = {
    target: relative,
    session,
    acquired_at: now,
    expires_at: now + LEASE_TTL_MS,
    state: 'held',
  };
  await ctx.fs.writeText(target, `${JSON.stringify(lease)}\n`, undefined, undefined, policy);
  return {target, lease};
}

async function releaseLease(ctx, lease, now, policy) {
  if (!lease) return;
  try {
    await ctx.fs.writeText(lease.target, `${JSON.stringify({
      ...lease.lease, state: 'released', released_at: now,
    })}\n`, undefined, undefined, policy);
  } catch {
    // A lease nobody released simply expires; failing the write here would
    // report a successful write as an error.
  }
}

/**
 * Locate a quoted fragment in the product, without asking a model.
 *
 * The finding says which file it is talking about and quotes the code verbatim;
 * the tool finds that quote and writes the line. A quote that does not appear,
 * or that appears in more than one place, is refused instead of resolved: an
 * anchor that cannot be placed is an anchor that would point at an unrelated
 * line while looking perfectly located, which is exactly the failure mode this
 * replaces. A finding about something with no location carries no anchor, and
 * that is honest rather than a gap.
 */
function locateExcerpt(content, excerpt) {
  const lines = (text) => text.replace(/\r\n?/g, '\n').split('\n').map((line) => line.replace(/\s+$/, ''));
  const haystack = lines(content);
  // Only the tail is trimmed: a quote keeps the indentation it was copied with,
  // because in most languages that indentation is part of what it says.
  const needle = lines(excerpt.trimEnd());
  const matches = [];
  for (let index = 0; index + needle.length <= haystack.length; index++) {
    if (needle.every((line, offset) => haystack[index + offset] === line)) matches.push(index + 1);
  }
  return matches;
}

async function readProductFile(ctx, productPath, relative, signal) {
  if (TRAVERSAL.test(String(relative).replace(/\\/g, '/'))) {
    throw new Error(`evidence.path sale del producto: ${relative}`);
  }
  const target = await ctx.fs.resolve(String(relative), { cwd: productPath, signal });
  const info = await ctx.fs.stat(target, signal);
  if (info?.type !== 'file') {
    throw new Error(`evidence.path no es un fichero real: ${relative}`);
  }
  if (typeof info.size === 'number' && info.size > ANCHORED_FILE_BYTE_LIMIT) {
    throw new Error(`evidence.path excede el límite verificable: ${relative}`);
  }
  const text = await ctx.fs.readText(target, signal);
  if (typeof text !== 'string') {
    throw new Error(`evidence.path no se puede leer: ${relative}`);
  }
  return text;
}

async function validateManagedFindings(ctx, target, content, signal) {
  if (typeof ctx.fs.processPath !== 'function' || typeof ctx.fs.readText !== 'function') return undefined;
  const rawTargetPath = await ctx.fs.processPath(target);
  if (typeof rawTargetPath !== 'string') return undefined;
  const targetPath = rawTargetPath.replace(/\\/g, '/').replace(/\/+$/, '');
  if (!targetPath.endsWith(MANAGED_FINDINGS_SUFFIX)) return undefined;

  const workspacePath = targetPath.slice(0, -MANAGED_FINDINGS_SUFFIX.length);
  const expectedTarget = await ctx.fs.resolve('mode-state/findings.jsonl', {
    cwd: workspacePath, signal,
  });
  if (!expectedTarget || expectedTarget.targetKey !== target.targetKey) {
    throw new Error('findings target no coincide con el mode-state gestionado');
  }
  const plan = await loadSignedPlan(ctx, workspacePath, signal);
  const productPath = typeof plan.product === 'string' ? plan.product.replace(/\/+$/, '') : null;
  if (!productPath) throw new Error('capability-plan no declara el producto');

  const lines = content.endsWith('\n') ? content.slice(0, -1).split('\n') : content.split('\n');
  if (lines.length === 1 && lines[0] === '') return undefined;
  if (lines.some((line) => line.trim() === '')) throw new Error('findings contiene línea vacía');

  const rewritten = [];
  for (let index = 0; index < lines.length; index++) {
    let record;
    try { record = JSON.parse(lines[index]); } catch { throw new Error(`finding ${index} inválido`); }
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error(`finding ${index} inválido`);
    }
    const allowed = [...FINDING_FIELDS, 'evidence'];
    if (Object.keys(record).some((key) => !allowed.includes(key))) {
      throw new Error(`finding ${index} no cumple el schema estricto`);
    }
    if (typeof record.finding_id !== 'string' || record.finding_id.length === 0
        || !REVISION.test(String(record.base_revision))
        || !SEVERITIES.includes(record.severity)
        || !STATUSES.includes(record.status)
        || typeof record.summary !== 'string' || record.summary.length === 0) {
      throw new Error(`finding ${index} no cumple el schema estricto`);
    }
    for (const [field, limit] of [['cause', CAUSE_MAX_BYTES], ['prevention', PREVENTION_MAX_BYTES]]) {
      const value = record[field];
      if (value === undefined) continue;
      if (typeof value !== 'string' || value.length === 0
          || Buffer.byteLength(value, 'utf8') > limit) {
        throw new Error(`finding ${index}: ${field} debe ser texto de 1 a ${limit} bytes`);
      }
    }
    // A record over the cap would be dropped by the next preflight, long after
    // the turn that wrote it, so the refusal happens where the model can act.
    const encoded = Buffer.byteLength(JSON.stringify(record), 'utf8');
    if (encoded + 32 > RECORD_BYTE_LIMIT) {
      throw new Error(`finding ${index} ocupa ${encoded} bytes y el tope del registro es `
        + `${RECORD_BYTE_LIMIT}; acorta summary, cause o prevention`);
    }
    const evidence = record.evidence;
    if (evidence === undefined) {
      rewritten.push(record);
      continue;
    }
    if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) {
      throw new Error(`finding ${index}: evidence debe ser objeto o estar ausente`);
    }
    const evidenceKeys = Object.keys(evidence).sort();
    if (evidenceKeys.length < 2
        || !evidenceKeys.includes('excerpt') || !evidenceKeys.includes('path')
        || evidenceKeys.some((key) => !['excerpt', 'fingerprint', 'line', 'located', 'path'].includes(key))) {
      throw new Error(`finding ${index}: evidence debe llevar exactamente path y excerpt`);
    }
    // line, located and fingerprint are computed here; a mode that writes them
    // is claiming an identity or a location it did not derive.
    if ('line' in evidence || 'located' in evidence || 'fingerprint' in evidence) {
      throw new Error(`finding ${index}: evidence.line, evidence.located y evidence.fingerprint `
        + 'los calcula la herramienta');
    }
    if (typeof evidence.path !== 'string' || evidence.path.length === 0
        || typeof evidence.excerpt !== 'string'
        || Buffer.byteLength(evidence.excerpt, 'utf8') < ANCHOR_EXCERPT_MIN) {
      throw new Error(`finding ${index}: evidence necesita path y un excerpt de al menos ${ANCHOR_EXCERPT_MIN} bytes`);
    }
    const source = await readProductFile(ctx, productPath, evidence.path, signal);
    const matches = locateExcerpt(source, evidence.excerpt);
    if (matches.length === 0) {
      throw new Error(`finding ${index} (${record.finding_id}): el excerpt no aparece en ${evidence.path}`);
    }
    if (matches.length > 1) {
      throw new Error(`finding ${index} (${record.finding_id}): el excerpt aparece ${matches.length} veces en ${evidence.path}; `
        + 'cita un fragmento que sea único');
    }
    const computed = {
      finding_id: record.finding_id,
      base_revision: record.base_revision,
      severity: record.severity,
      summary: record.summary,
      status: record.status,
      evidence: {
        path: evidence.path,
        excerpt: evidence.excerpt,
        // Identity of the quoted code, not of the wording: two audits that
        // describe the same line differently share a fingerprint, which is
        // what makes "same defect, other words" countable.
        fingerprint: createHash('sha256')
          .update(`${evidence.path}\n${evidence.excerpt.trimEnd()}`, 'utf8').digest('hex'),
        line: matches[0],
        located: true,
      },
    };
    if (record.cause !== undefined) computed.cause = record.cause;
    if (record.prevention !== undefined) computed.prevention = record.prevention;
    rewritten.push(computed);
  }
  return rewritten.map((record) => JSON.stringify(record)).join('\n') + '\n';
}

/**
 * A handoff is the claim that the audit happened, so it is checked against the
 * findings the state actually carries: every id it names must exist at the same
 * base, and the audit handoff (the one carrying the exact contract next_prompt)
 * must name every finding left OPEN at that base. Syncify is the case this
 * closes — six consecutive findings had a work item and no repair handoff
 * covering them, because nothing compared the two files before accepting the
 * turn. Refusing the write keeps the unclaimed findings in the state instead of
 * in a response nobody can re-derive.
 */
async function validateManagedHandoff(ctx, target, content, signal) {
  if (typeof ctx.fs.processPath !== 'function' || typeof ctx.fs.readText !== 'function') return;
  const rawTargetPath = await ctx.fs.processPath(target);
  if (typeof rawTargetPath !== 'string') return;
  const targetPath = rawTargetPath.replace(/\\/g, '/').replace(/\/+$/, '');
  if (!targetPath.endsWith(MANAGED_HANDOFFS_SUFFIX)) return;

  const workspacePath = targetPath.slice(0, -MANAGED_HANDOFFS_SUFFIX.length);
  const expectedTarget = await ctx.fs.resolve('mode-state/handoffs.jsonl', {
    cwd: workspacePath, signal,
  });
  if (!expectedTarget || expectedTarget.targetKey !== target.targetKey) {
    throw new Error('handoffs target no coincide con el mode-state gestionado');
  }
  const findingsTarget = await ctx.fs.resolve('mode-state/findings.jsonl', {
    cwd: workspacePath, signal,
  });
  let findingsText;
  try {
    findingsText = await ctx.fs.readText(findingsTarget, signal);
  } catch {
    findingsText = null;
  }
  if (typeof findingsText === 'string' && Buffer.byteLength(findingsText, 'utf8') > FINDINGS_BYTE_LIMIT) {
    throw new Error('findings.jsonl del mode-state excede el límite gestionado');
  }
  const findings = [];
  if (typeof findingsText === 'string') {
    const lines = findingsText.split('\n');
    for (let index = 0; index < lines.length; index++) {
      if (lines[index].trim() === '') continue;
      let record;
      try { record = JSON.parse(lines[index]); } catch {
        throw new Error(`findings.jsonl:${index + 1} no es JSON`);
      }
      if (!record || typeof record !== 'object' || Array.isArray(record)) {
        throw new Error(`findings.jsonl:${index + 1} no es objeto`);
      }
      findings.push(record);
    }
  }

  const lines = content.endsWith('\n') ? content.slice(0, -1).split('\n') : content.split('\n');
  if (lines.length === 1 && lines[0] === '') return;
  if (lines.some((line) => line.trim() === '')) throw new Error('handoffs contiene línea vacía');
  for (let index = 0; index < lines.length; index++) {
    let record;
    try { record = JSON.parse(lines[index]); } catch { throw new Error(`handoff ${index} inválido`); }
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error(`handoff ${index} inválido`);
    }
    const keys = Object.keys(record).sort();
    const required = ['base_revision', 'finding_ids', 'handoff_id', 'next_prompt'];
    if (keys.length !== required.length || keys.some((key, offset) => key !== required[offset])
        || typeof record.handoff_id !== 'string' || record.handoff_id.length === 0
        || typeof record.next_prompt !== 'string' || record.next_prompt.length === 0
        || typeof record.base_revision !== 'string' || !REVISION.test(record.base_revision)
        || !Array.isArray(record.finding_ids)
        || record.finding_ids.some((id) => typeof id !== 'string' || id.length === 0)) {
      throw new Error(`handoff ${index} no cumple el schema estricto`);
    }
    if (new Set(record.finding_ids).size !== record.finding_ids.length) {
      throw new Error(`handoff ${index} repite finding_id`);
    }
    const persisted = new Set(findings.filter((finding) => (
      finding.base_revision === record.base_revision
      && typeof finding.finding_id === 'string')).map((finding) => finding.finding_id));
    const missing = record.finding_ids.filter((id) => !persisted.has(id));
    if (missing.length > 0) {
      throw new Error(`handoff ${index} nombra hallazgos no persistidos en esa base: ${missing.join(',')}`);
    }
    if (record.next_prompt !== AUDIT_NEXT_PROMPT) continue;
    const open = new Set(findings.filter((finding) => (
      finding.base_revision === record.base_revision && finding.status === 'OPEN'
      && typeof finding.finding_id === 'string')).map((finding) => finding.finding_id));
    const uncovered = [...open].filter((id) => !record.finding_ids.includes(id)).sort();
    const extraneous = record.finding_ids.filter((id) => !open.has(id)).sort();
    if (uncovered.length > 0 || extraneous.length > 0) {
      throw new Error(`handoff ${index} no cubre exactamente los hallazgos OPEN de la base`
        + `${uncovered.length > 0 ? `; sin nombrar: ${uncovered.join(',')}` : ''}`
        + `${extraneous.length > 0 ? `; no OPEN: ${extraneous.join(',')}` : ''}`);
    }
  }
}

export function apply(ctx, config) {
  const MODES = ['workspace-write', 'danger-full-access'];
  const policyService = () => ctx.get('sandboxPolicy');

  async function resolvePolicy(toolName, args, exec) {
    const policy = policyService().resolve(exec?.agent?.session ? { session: exec.agent.session } : {});
    const requested = args?.sandbox_permissions;
    if (requested === undefined || requested === null) return policy;
    if (typeof requested !== 'string' || !MODES.includes(requested)) {
      throw new Error(`sandbox_permissions inválido: ${String(requested)}`);
    }
    if (requested === policy.mode) return policy;            // corrección M7: mismo modo no es escalada
    if (requested === 'workspace-write' && policy.mode === 'danger-full-access') return policy;
    // estrictamente mayor: secuencia de aprobación fail-closed del servicio approval
    const approver = ctx.get('approval');
    const outcome = await approver.request({
      agent: exec.agent, toolName, callId: exec.callId, signal: exec.signal,
      reason: `escalate sandbox to ${requested}: ${args?.justification || 'sin justificación'}`,
    });
    if (outcome !== 'allowed-once') {
      throw new Error(`sandbox escalation to "${requested}" denied (outcome: ${outcome})`);
    }
    return { ...policy, mode: requested };
  }

  // Guard global (monotónico: solo deniega). Corre en pre-execute, antes de
  // validateBashArgs y de approveEscalation, así el modelo recibe el mensaje
  // correctivo y no el error confuso de upstream.
  ctx.tools.guard?.((exec) => {
    if (exec?.name !== 'bash' && exec?.name !== 'pwsh') return undefined;
    const args = exec.arguments;
    const requested = args?.sandbox_permissions;
    const justification = args?.justification;
    if (requested === undefined && justification === undefined) return undefined;
    return 'forbidden escalation channel: sandbox_permissions and justification are not accepted in this deployment; RETAINED with no retry after denial or schema error.';
  });

  // Corrección M9: barrer las definiciones ya registradas y retirar del
  // esquema model-facing los parámetros de escalada y su narrativa. El
  // registro expone las definiciones por referencia y el proveedor de
  // systemPrompt.tools las re-proyecta en cada request, así que la mutación
  // alcanza a la vista del modelo en la siguiente petición. Orden: este
  // plugin se aplica después de las filas de tools del preset (el patch se
  // inserta al final); si una herramienta no existe en la composición, se
  // omite sin ruido.
  const sanitizeDescription = (text) => {
    if (typeof text !== 'string') return text;
    const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z`$])/);
    const kept = sentences.filter((s) => !/escalat|sandbox_permissions|justification/i.test(s));
    return kept.length > 0 ? kept.join(' ') : text;
  };
  const stripEscalation = (definition) => {
    const params = definition?.parameters;
    if (!params || typeof params !== 'object' || !params.properties) return false;
    if (!('sandbox_permissions' in params.properties) && !('justification' in params.properties)) return false;
    delete params.properties.sandbox_permissions;
    delete params.properties.justification;
    if (Array.isArray(params.required)) {
      params.required = params.required.filter((k) => k !== 'sandbox_permissions' && k !== 'justification');
      if (params.required.length === 0) delete params.required;
    }
    if (typeof definition.description === 'string') {
      definition.description = sanitizeDescription(definition.description);
    }
    return true;
  };
  // Variante no mutante para las schemas clonadas del assembly.
  const stripToolSchema = (tool) => {
    if (!tool || typeof tool !== 'object') return tool;
    const params = tool.parameters;
    if (!params || typeof params !== 'object' || !params.properties) return tool;
    if (!('sandbox_permissions' in params.properties) && !('justification' in params.properties)) return tool;
    const properties = { ...params.properties };
    delete properties.sandbox_permissions;
    delete properties.justification;
    const cleanedParams = { ...params, properties };
    if (Array.isArray(cleanedParams.required)) {
      const required = cleanedParams.required.filter((k) => k !== 'sandbox_permissions' && k !== 'justification');
      if (required.length > 0) cleanedParams.required = required;
      else delete cleanedParams.required;
    }
    const cleaned = { ...tool, parameters: cleanedParams };
    if (typeof cleaned.description === 'string') {
      cleaned.description = sanitizeDescription(cleaned.description);
    }
    return cleaned;
  };
  let stripped = [];
  for (const toolName of ['bash', 'pwsh', 'write', 'edit']) {
    try {
      const definition = ctx.tools.get?.(toolName);
      if (definition && stripEscalation(definition)) stripped.push(toolName);
    } catch {
      // herramienta ausente en esta composición: nada que sanear
    }
  }

  // Corrección M9 (vía por-request, la efectiva): el waterfall
  // system-prompt/assemble es autoritario y assembly.tools alimenta
  // directamente el array de function-calling de cada petición. Sanea también
  // para subagentes y para tools registradas después de este apply.
  let notified = false;
  try {
    ctx.on?.('system-prompt/assemble', async (_assembly, _context, next) => {
      const assembled = await next();
      if (!assembled || !Array.isArray(assembled.tools)) return assembled;
      let changed = false;
      const tools = assembled.tools.map((tool) => {
        const cleaned = stripToolSchema(tool);
        if (cleaned !== tool) changed = true;
        return cleaned;
      });
      if (changed && !notified) {
        notified = true;
        console.warn('[workflow-write] M9: parámetros de escalada retirados del esquema model-facing');
      }
      return changed ? { ...assembled, tools } : assembled;
    });
  } catch {
    // sin servicio de eventos en esta composición: queda el barrido de apply
  }

  // Esquema CRUDO ya compilado: es la forma que register() consume tal cual.
  const parameters = {
    type: 'object',
    properties: {
      file_path: { type: 'string', description: 'Ruta a escribir, resuelta por el backend de filesystem.' },
      content: { type: 'string', description: 'Contenido UTF-8 completo a escribir.' },
    },
    required: ['file_path', 'content'],
  };

  ctx.tools.register({
    name: 'workflow_write',
    description: 'Crea o reemplaza completamente un archivo de texto UTF-8 dentro del área escribible de la sesión.',
    parameters,
    output: {
      schema: {
        type: 'object', additionalProperties: false,
        required: ['path', 'operation', 'before', 'after'],
        properties: {
          path: { type: 'string' },
          operation: { type: 'string', enum: ['create', 'update'] },
          before: { oneOf: [{ type: 'string' }, { type: 'null' }] },
          after: { type: 'string' },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: `<path>${value.path}</path>\n<type>file</type>\n<content>\n${value.operation === 'create' ? 'Created' : 'Updated'} file\n</content>`,
      }],
    },
    async execute(args, exec) {
      if (typeof args?.file_path !== 'string' || args.file_path.trim().length === 0) {
        throw new Error('file_path debe ser un string no vacío');
      }
      if (typeof args?.content !== 'string') throw new Error('content debe ser un string');
      const policy = await resolvePolicy('workflow_write', args, exec);
      // Espejo de sessionResolveOptions de dsh-tool-fs: cwd = raíz de la
      // política o cwd de la sesión; upstream además canónica el cwd con
      // segmentos padre, caso límite que aquí se omite.
      const cwd = policy?.workspaceRoot ?? exec?.agent?.session?.header?.cwd;
      const target = await ctx.fs.resolve(args.file_path, {
        ...(cwd !== undefined ? { cwd } : {}),
        signal: exec.signal,
      });
      // Una sesión gestionada declara su raíz de estado; la herramienta la
      // impone en vez de confiar en que el modelo respete el contrato (SR-3).
      const stateRoot = await managedStateRoot(ctx, cwd, exec.signal);
      if (stateRoot) {
        await assertStateWrite(ctx, target, stateRoot,
          `${stateRoot.slice(0, -STATE_DIR_NAME.length)}${EVIDENCE_DIR_NAME}`,
          args.content);
      }
      await validateManagedVerification(ctx, target, args.content, exec.signal);
      await validateManagedHandoff(ctx, target, args.content, exec.signal);
      // The findings gate resolves every anchor and returns the rewritten
      // content, because the line a finding claims is the line the tool
      // computed, not the one the mode wrote.
      const anchored = await validateManagedFindings(ctx, target, args.content, exec.signal);
      const content = anchored ?? args.content;
      // The lease only covers a replacement of one state file: an unidentified
      // session takes no lease rather than a shared one, because a lock
      // everybody holds is a lock nobody holds.
      const session = leaseIdentity(exec);
      const relative = stateRoot && targetPathUnder(stateRoot, target);
      const now = Date.now();
      let lease = null;
      if (session && relative) {
        lease = await acquireLease(ctx, stateRoot, relative, session, now, policy);
      }
      const intent = await ctx.waterfall('fs/write-intent', target, exec, () => undefined);
      // Sin envoltura de error propia: los errores del backend ya traen el
      // marcador [sandbox: ...] cuando son denegaciones; envolver aquí cualquier
      // fallo los falsearía como denegaciones de política.
      let outcome;
      try {
        outcome = await ctx.fs.writeText(target, content, intent, exec.signal, policy);
      } finally {
        await releaseLease(ctx, lease, Date.now(), policy);
      }
      ctx.emit('fs/observed', target, { kind: 'present', version: outcome.version }, exec);
      return { path: target.displayPath, operation: outcome.operation, before: outcome.before, after: outcome.after };
    },
    presentCall(args) {
      return { card: 'diff', title: `Write ${args?.file_path}`,
        diffs: [{ path: args?.file_path, oldText: null, newText: args?.content }],
        locations: args?.file_path ? [{ path: args.file_path }] : [] };
    },
  });
}
