/** Parser ANSI sin dependencias React (testeable con node). */

const ANSI_RE = /\x1b\[([\d;]*)m|\x9b([\d;]*)m/g;

export function stripAnsi(text: string): string {
  return text.replace(ANSI_RE, '');
}

export function hasAnsiCodes(text: string): boolean {
  return /\x1b\[[\d;]*m|\x9b[\d;]*m/.test(text);
}

/**
 * Categorías "fuertes": deben ganar incluso si la línea trae códigos ANSI
 * incrustados (p. ej. el segmento `@alias (chat_id)` que logger.py colorea en
 * TODAS las líneas [REQ]/[PLAN]/[TOOL]/[SYS] — eso hacía que hasAnsiCodes()
 * devolviera true para la línea entera y nunca se llegara a este archivo).
 */
export function strongLogCategoryClass(line: string): string | null {
  const t = line.trim();
  // harness_metric payloads carry field names like "risk_denied"/"failures": 0 —
  // check first so those don't fall through to the error/warn substring checks below.
  if (/harness_metric/i.test(t)) {
    return 'text-emerald-700 dark:text-emerald-300';
  }
  if (/error|exception|traceback|fatal|errno|failed|failure|refused|denied/i.test(t)) {
    return 'text-red-700 dark:text-red-400';
  }
  if (/warn|warning|offline|timeout|retry|unavailable/i.test(t)) {
    return 'text-amber-700 dark:text-amber-300';
  }
  if (/\[TOOL\]|\[PLAN\]|tool_usage:|\btool=/i.test(t)) {
    return 'text-yellow-700 dark:text-yellow-300';
  }
  return null;
}

export function colorizePlainLogLine(line: string): { className: string; text: string } {
  const strong = strongLogCategoryClass(line);
  if (strong) {
    return { className: strong, text: line };
  }
  const t = line.trim();
  if (/^\d+\|/.test(t) || /\[PM2\]/i.test(t)) {
    return { className: 'text-emerald-700 dark:text-emerald-300', text: line };
  }
  if (/info|notice/i.test(t)) {
    return { className: 'text-sky-800 dark:text-sky-300', text: line };
  }
  if (/debug|verbose/i.test(t)) {
    return { className: 'text-gov-gray-600 dark:text-slate-400', text: line };
  }
  return { className: 'text-gov-gray-800 dark:text-slate-200', text: line };
}
