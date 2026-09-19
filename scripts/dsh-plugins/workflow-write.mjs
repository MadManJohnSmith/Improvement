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
    const corrective = 'Este despliegue no admite escalada por parámetros: reenvía exactamente el mismo comando omitiendo sandbox_permissions y justification; el modo vigente ya cubre el workspace de la sesión, y una denegación real de sandbox se informa como [sandbox: ...], nunca escalando.';
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
