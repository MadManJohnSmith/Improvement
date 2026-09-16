/**
 * workflow-write: herramienta de escritura con semántica de escalada corregida.
 *
 * Defecto del runtime observado (M7, 2026-09-13): `write` de @deepseek-ai/dsh-tool-fs
 * rechaza «not strictly wider» cuando el modelo envía sandbox_permissions igual al modo
 * ya vigente, bloqueando toda escritura con enforcement completo. Este plugin registra
 * `workflow_write` con la MISMA ejecución que upstream (ctx.fs.writeText + observación)
 * y una corrección única en el resolver de política:
 *   - sin parámetros de escalada  -> política vigente;
 *   - modo solicitado == vigente  -> política vigente (no es una escalada);
 *   - modo estrictamente mayor    -> validate + aprobación real del servicio `approval`;
 *   - modo menor                  -> política vigente (más estrecho no concede nada).
 * Sin aprobación, falla cerrado; el aislamiento no se debilita: la ejecución siempre
 * pasa por ctx.fs.writeText con la política resuelta, igual que upstream.
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

  const parameters = {
    file_path: { type: 'string', required: true, description: 'Ruta a escribir, resuelta por el backend de filesystem.' },
    content: { type: 'string', required: true, description: 'Contenido UTF-8 completo a escribir.' },
    sandbox_permissions: { type: 'string', required: false, enum: MODES,
      description: 'Opcional. Solo para escalar a un modo ESTRICTAMENTE mayor del vigente; con el modo vigente ya alcanza y no debe enviarse.' },
    justification: { type: 'string', required: false, description: 'Una frase de justificación, solo junto a sandbox_permissions.' },
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
      const target = await ctx.fs.resolve(args.file_path);
      const intent = await ctx.waterfall('fs/write-intent', target, exec, () => undefined);
      let outcome;
      try {
        outcome = await ctx.fs.writeText(target, args.content, intent, exec.signal, policy);
      } catch (error) {
        throw new Error(`[sandbox: operación denegada bajo el modo ${policy?.mode || 'desconocido'}] ${error?.message || error}`);
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
