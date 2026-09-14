/** Heuristic context composition from the gateway (chars/4 + tool-schema reserve). */

export type ContextTokenBreakdown = {
  system: number;
  messages: number;
  tools: number;
  tool_results?: number;
  tool_schemas?: number;
  total: number;
};

export function normalizeContextTokenBreakdown(
  raw?: Record<string, number> | null
): ContextTokenBreakdown | null {
  if (!raw || typeof raw !== 'object') return null;
  const system = Math.max(0, Math.floor(Number(raw.system) || 0));
  const messages = Math.max(0, Math.floor(Number(raw.messages) || 0));
  const tools = Math.max(0, Math.floor(Number(raw.tools) || 0));
  const tool_results = Math.max(0, Math.floor(Number(raw.tool_results) || 0));
  const tool_schemas = Math.max(0, Math.floor(Number(raw.tool_schemas) || 0));
  let total = Math.max(0, Math.floor(Number(raw.total) || 0));
  if (total <= 0) total = system + messages + tools;
  if (total <= 0 && system <= 0 && messages <= 0 && tools <= 0) return null;
  return { system, messages, tools, tool_results, tool_schemas, total };
}
