const MARKDOWN_SIGNALS: RegExp[] = [
  /^#{1,6}\s/m,
  /^\s*[-*+]\s+/m,
  /^\s*\d+\.\s+/m,
  /```/,
  /^\s*>/m,
  /\*\*[^*\n]+\*\*/,
  /\[[^\]]+\]\([^)]+\)/,
  /^\|[^|\n]+\|/m,
  /^---+\s*$/m,
];

/** Heurística conservadora: solo formatear si hay señales claras de Markdown. */
export function looksLikeMarkdown(text: string): boolean {
  const trimmed = (text || '').trim();
  if (!trimmed) return false;
  return MARKDOWN_SIGNALS.some((pattern) => pattern.test(trimmed));
}
