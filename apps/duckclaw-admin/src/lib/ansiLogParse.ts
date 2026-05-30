/** Parser ANSI sin dependencias React (testeable con node). */

const ANSI_RE = /\x1b\[([\d;]*)m|\x9b([\d;]*)m/g;

export function stripAnsi(text: string): string {
  return text.replace(ANSI_RE, '');
}

export function hasAnsiCodes(text: string): boolean {
  return /\x1b\[[\d;]*m|\x9b[\d;]*m/.test(text);
}

export function colorizePlainLogLine(line: string): { className: string; text: string } {
  const t = line.trim();
  if (/error|exception|traceback|fatal|errno/i.test(t)) {
    return { className: 'text-red-400', text: line };
  }
  if (/warn|warning/i.test(t)) {
    return { className: 'text-amber-300', text: line };
  }
  if (/^\d+\|/.test(t) || /\[PM2\]/i.test(t)) {
    return { className: 'text-emerald-300', text: line };
  }
  if (/info|notice/i.test(t)) {
    return { className: 'text-sky-300', text: line };
  }
  if (/debug|verbose/i.test(t)) {
    return { className: 'text-slate-400', text: line };
  }
  return { className: 'text-slate-200', text: line };
}
