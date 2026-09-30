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
export const inject = ['tools', 'fs', 'systemPrompt'];

const MANAGED_RESULTS_SUFFIX = '/mode-state/verification-results.jsonl';
const PLAN_RELATIVE = '.dsh-managed/capability-plan.json';
const PLAN_BYTE_LIMIT = 131072;
const STATE_DIR_NAME = 'mode-state';
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

async function assertStateWrite(ctx, target, stateRoot) {
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
  if (candidate !== stateRoot && !candidate.startsWith(`${stateRoot}/`)) {
    throw new Error(`workflow_write: la escritura de estado sale de ${stateRoot}: ${candidate}; `
      + 'denegado sin reintento');
  }
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
    const required = ['candidate_head', 'command', 'finding_id', 'result'];
    if (keys.length !== required.length || keys.some((key, offset) => key !== required[offset])
        || typeof record.finding_id !== 'string' || record.finding_id.length === 0
        || typeof record.candidate_head !== 'string'
        || !/^[0-9a-f]{40,64}$/.test(record.candidate_head)) {
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
      if (stateRoot) await assertStateWrite(ctx, target, stateRoot);
      await validateManagedVerification(ctx, target, args.content, exec.signal);
      const intent = await ctx.waterfall('fs/write-intent', target, exec, () => undefined);
      // Sin envoltura de error propia: los errores del backend ya traen el
      // marcador [sandbox: ...] cuando son denegaciones; envolver aquí cualquier
      // fallo los falsearía como denegaciones de política.
      const outcome = await ctx.fs.writeText(target, args.content, intent, exec.signal, policy);
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
