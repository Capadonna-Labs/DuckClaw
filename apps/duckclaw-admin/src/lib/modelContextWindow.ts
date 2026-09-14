/** Heuristic context-window sizes for common chat models (tokens). */

const MODEL_CONTEXT_WINDOW: Array<{ match: RegExp; tokens: number }> = [
  { match: /claude-(?:opus|sonnet)-4|claude-4/i, tokens: 1_000_000 },
  { match: /claude-3(?:\.[05])?-opus|claude-3-opus/i, tokens: 200_000 },
  { match: /claude-3(?:\.[05])?-sonnet|claude-3-5-sonnet|claude-3-7-sonnet/i, tokens: 200_000 },
  { match: /claude-3(?:\.[05])?-haiku|claude-3-haiku/i, tokens: 200_000 },
  { match: /gpt-5|o3|o4-mini/i, tokens: 200_000 },
  { match: /gpt-4\.1|gpt-4o/i, tokens: 128_000 },
  { match: /gpt-4-turbo|gpt-4-1106|gpt-4-0125/i, tokens: 128_000 },
  { match: /gpt-4(?!o)/i, tokens: 8_192 },
  { match: /gpt-3\.5-turbo-16k/i, tokens: 16_384 },
  { match: /gpt-3\.5/i, tokens: 16_385 },
  { match: /gemini-2\.5|gemini-2\.0|gemini-1\.5-pro/i, tokens: 1_000_000 },
  { match: /gemini-1\.5-flash/i, tokens: 1_000_000 },
  { match: /deepseek/i, tokens: 128_000 },
  { match: /qwen.*72b|qwen2\.5/i, tokens: 128_000 },
  { match: /llama-3\.1|llama3\.1/i, tokens: 128_000 },
  { match: /mistral-large|mistral-small/i, tokens: 128_000 },
];

/** Best-effort context window for a model id; null if unknown. */
export function inferModelContextWindow(model?: string | null): number | null {
  const id = (model || '').trim();
  if (!id) return null;
  for (const row of MODEL_CONTEXT_WINDOW) {
    if (row.match.test(id)) return row.tokens;
  }
  return null;
}

/** Compact count for pills: 381458 → "381k", 194700 → "194.7k", 1200 → "1.2k". */
export function formatCompactTokenCount(total: number): string {
  const n = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  if (n < 1_000) return String(n);
  if (n < 10_000) {
    const k = n / 1_000;
    return `${k.toFixed(k >= 10 ? 0 : 1).replace(/\.0$/, '')}k`;
  }
  if (n < 1_000_000) return `${Math.round(n / 1_000)}k`;
  const m = n / 1_000_000;
  return `${m.toFixed(m >= 10 ? 0 : 1).replace(/\.0$/, '')}M`;
}
