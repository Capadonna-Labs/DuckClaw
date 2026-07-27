export type UsageTokenBreakdown = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export function formatTokenCount(total: number): string {
  const n = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  if (n === 0) return '0 tokens';
  return `${n.toLocaleString('es-CO')} tokens`;
}

/** Same shape as gateway log line: total [P:prompt, C:completion]. */
export function normalizeUsageTokens(
  usage?: Record<string, number> | null
): UsageTokenBreakdown | null {
  if (!usage || typeof usage !== 'object') return null;
  const input = Number(usage.input_tokens ?? usage.prompt_tokens ?? 0);
  const output = Number(usage.output_tokens ?? usage.completion_tokens ?? 0);
  let total = Number(usage.total_tokens ?? 0);
  if (!Number.isFinite(total) || total <= 0) total = input + output;
  if ((!Number.isFinite(input) || input < 0) && (!Number.isFinite(output) || output < 0)) {
    return null;
  }
  const inp = Math.max(0, Math.floor(Number.isFinite(input) ? input : 0));
  const out = Math.max(0, Math.floor(Number.isFinite(output) ? output : 0));
  const tot = Math.max(0, Math.floor(Number.isFinite(total) && total > 0 ? total : inp + out));
  if (tot <= 0 && inp <= 0 && out <= 0) return null;
  return { input_tokens: inp, output_tokens: out, total_tokens: tot };
}

export function formatUsageTokensLogLine(usage: UsageTokenBreakdown): string {
  const total = usage.total_tokens.toLocaleString('es-CO');
  const prompt = usage.input_tokens.toLocaleString('es-CO');
  const completion = usage.output_tokens.toLocaleString('es-CO');
  return `Tokens: ${total} [P:${prompt}, C:${completion}]`;
}

export function accumulateUsageTokens(
  current: number,
  usage?: Record<string, number> | null
): number {
  const normalized = normalizeUsageTokens(usage);
  if (!normalized || normalized.total_tokens <= 0) return current;
  return current + normalized.total_tokens;
}
