export function formatTokenCount(total: number): string {
  const n = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  if (n === 0) return '0 tokens';
  return `${n.toLocaleString('es-CO')} tokens`;
}

export function accumulateUsageTokens(
  current: number,
  usage?: Record<string, number> | null
): number {
  if (!usage || typeof usage !== 'object') return current;
  const delta =
    Number(usage.total_tokens) ||
    Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0) ||
    0;
  if (!Number.isFinite(delta) || delta <= 0) return current;
  return current + Math.floor(delta);
}
