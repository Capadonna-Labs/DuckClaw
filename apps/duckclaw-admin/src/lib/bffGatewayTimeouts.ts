/** Tiered gateway proxy timeouts for the admin BFF catch-all route. */

export const BFF_TIMEOUT_FAST_MS = 8_000;
export const BFF_TIMEOUT_DEFAULT_GET_MS = 30_000;
export const BFF_TIMEOUT_DEFAULT_WRITE_MS = 45_000;
export const BFF_TIMEOUT_HEALTH_MS = 10_000;
export const BFF_TIMEOUT_KNOWLEDGE_MUTATION_MS = 120_000;
export const BFF_TIMEOUT_OPS_MS = 60_000;
/** Post-turn LLM chips; gateway can be busy after a long worker turn. */
export const BFF_TIMEOUT_CHAT_SUGGESTIONS_MS = 120_000;

export function bffGatewayTimeoutMs(sub: string, method: string): number {
  const verb = method.toUpperCase();
  const path = (sub || '').replace(/^\/+|\/+$/g, '');

  if (path === 'health' || path === 'bootstrap/status') {
    return BFF_TIMEOUT_HEALTH_MS;
  }
  if (path.startsWith('auth/')) {
    return BFF_TIMEOUT_FAST_MS;
  }
  if (path.startsWith('playground/config')) {
    return BFF_TIMEOUT_DEFAULT_GET_MS;
  }
  // Suggestion chips are a separate LLM call after the turn; 45s default
  // write timeout aborts under load and the UI then wipes chips to [].
  if (path === 'chat/suggestions' || path.startsWith('chat/suggestions/')) {
    return BFF_TIMEOUT_CHAT_SUGGESTIONS_MS;
  }
  if (path.startsWith('knowledge/') && verb !== 'GET' && verb !== 'HEAD') {
    return BFF_TIMEOUT_KNOWLEDGE_MUTATION_MS;
  }
  if (path.startsWith('mcp/connectors/') && path.endsWith('/test')) {
    return 90_000;
  }
  if (path.startsWith('mcp/connectors/') && verb !== 'GET' && verb !== 'HEAD') {
    return 90_000;
  }
  if (path === 'ops/run') {
    return 240_000;
  }
  if (path === 'user-agents/draft') {
    return 120_000;
  }
  if (verb === 'GET' || verb === 'HEAD') {
    return BFF_TIMEOUT_DEFAULT_GET_MS;
  }
  return BFF_TIMEOUT_DEFAULT_WRITE_MS;
}
