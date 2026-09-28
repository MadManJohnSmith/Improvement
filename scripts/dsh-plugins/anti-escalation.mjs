/** Scoped guard for generated Improvement modes. */
export const inject = ['tools', 'systemPrompt'];

export function apply(ctx) {
  const forbidden = new Set(['sandbox_permissions', 'justification']);
  const cleanDescription = (text) => typeof text === 'string'
    ? text.split(/(?<=[.!?])\s+(?=[A-Z`$])/)
      .filter((part) => !/escalat|sandbox_permissions|justification/i.test(part)).join(' ')
    : text;
  const cleanTool = (tool) => {
    const params = tool?.parameters;
    if (!params?.properties || ![...forbidden].some((key) => key in params.properties)) return tool;
    const properties = Object.fromEntries(Object.entries(params.properties)
      .filter(([key]) => !forbidden.has(key)));
    const parameters = { ...params, properties };
    if (Array.isArray(parameters.required)) {
      parameters.required = parameters.required.filter((key) => !forbidden.has(key));
      if (parameters.required.length === 0) delete parameters.required;
    }
    return { ...tool, parameters, description: cleanDescription(tool.description) };
  };

  ctx.tools.guard?.((exec) => {
    if (!['bash', 'pwsh'].includes(exec?.name)) return undefined;
    if (![...forbidden].some((key) => exec.arguments?.[key] !== undefined)) return undefined;
    return 'forbidden escalation channel: sandbox_permissions and justification are prohibited for this Improvement mode; RETAINED with no retry after denial or schema error.';
  });

  ctx.on?.('system-prompt/assemble', async (_assembly, _context, next) => {
    const assembled = await next();
    if (!Array.isArray(assembled?.tools)) return assembled;
    return { ...assembled, tools: assembled.tools.map(cleanTool) };
  });
}
