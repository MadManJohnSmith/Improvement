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
 *     sandbox_permissions/justification defectuosas (justificación ausente o
 *     vacía, modo igual al vigente o más estrecho), se deniegan ANTES del
 *     dispatch con un mensaje correctivo, cortando el bucle de reintentos
 *     observado el 2026-09-19. Una escalada estrictamente mayor con
 *     justificación válida sigue su curso normal hacia la aprobación.
 *  4. execute replica la tool write de upstream: ctx.fs.resolve con opciones de
 *     sesión (cwd = raíz de la política o cwd de la sesión, señal de aborto),
 *     waterfall fs/write-intent, writeText con la política resuelta y emisión
 *     fs/observed. Los parámetros de escalada NO se publican en el esquema
 *     (las misiones prohíben enviarlos); quedan cubiertos por resolvePolicy si
 *     un modelo los fuerza.
 *
 * Sin aprobación, falla cerrado; el aislamiento no se debilita: la ejecución
 * siempre pasa por ctx.fs.writeText con la política resuelta, igual que upstream.
 */
export const inject = ['tools', 'fs', 'systemPrompt'];

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
    const corrective = 'Estos parámetros ya no forman parte del esquema de la herramienta en este despliegue: reenvía exactamente el mismo comando sin sandbox_permissions ni justification; el modo vigente ya cubre el workspace de la sesión, y una denegación real de sandbox se informa como [sandbox: ...], nunca escalando.';
    if (requested === undefined) {
      return `invalid escalation: justification solo es válida junto a sandbox_permissions. ${corrective}`;
    }
    if (justification === undefined || String(justification).trim().length === 0) {
      return `invalid escalation: sandbox_permissions requiere justification. ${corrective}`;
    }
    let policy;
    try {
      const service = policyService();
      policy = service?.resolve(exec?.agent?.session ? { session: exec.agent.session } : {});
    } catch {
      return undefined;
    }
    if (policy?.mode === undefined) return undefined;
    if (requested === policy.mode) {
      return `sandbox escalation to "${requested}" no es una escalada: ya es el modo vigente (defecto M7 de upstream). ${corrective}`;
    }
    if (requested === 'workspace-write' && policy.mode === 'danger-full-access') {
      return `sandbox escalation to "${requested}" es más estrecha que el modo vigente "${policy.mode}" y no concede nada. ${corrective}`;
    }
    return undefined; // estrictamente mayor: prosigue hacia la aprobación de upstream
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
