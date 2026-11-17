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

const cells = (row: string) => row.trim().replace(/^\||\|$/g, '').split('|');
const DELIM_ROW = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

/** GFM drops a table whose |---| row has a different column count than its header (the model miscounts);
 *  resize that row to the header's count, keeping the alignments it gave. */
export function fixTableDelimiterRows(text: string): string {
  const lines = text.split('\n');
  for (let i = 1; i < lines.length; i++) {
    if (!DELIM_ROW.test(lines[i]) || !lines[i - 1].includes('|')) continue;
    const n = cells(lines[i - 1]).length;
    const d = cells(lines[i]).map((c) => c.trim());
    if (d.length === n) continue;
    lines[i] = `|${Array.from({ length: n }, (_, k) => d[k] ?? '---').join('|')}|`;
  }
  return lines.join('\n');
}
