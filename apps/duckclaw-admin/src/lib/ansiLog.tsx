/** Convierte secuencias ANSI (estilo terminal macOS/PM2) a spans coloreados. */

import type { ReactNode } from 'react';
import { colorizePlainLogLine, hasAnsiCodes } from '@/lib/ansiLogParse';

const ANSI_RE =
  /\x1b\[([\d;]*)m|\x9b([\d;]*)m/g;

export { colorizePlainLogLine, hasAnsiCodes, stripAnsi } from '@/lib/ansiLogParse';

const FG: Record<number, string> = {
  30: '#94a3b8',
  31: '#f87171',
  32: '#4ade80',
  33: '#facc15',
  34: '#60a5fa',
  35: '#c084fc',
  36: '#22d3ee',
  37: '#f1f5f9',
  90: '#64748b',
  91: '#fca5a5',
  92: '#86efac',
  93: '#fde047',
  94: '#93c5fd',
  95: '#d8b4fe',
  96: '#67e8f9',
  97: '#ffffff',
};

type StyleState = {
  color?: string;
  bold?: boolean;
  dim?: boolean;
};

function applyCodes(state: StyleState, codes: number[]): StyleState {
  const next = { ...state };
  for (let i = 0; i < codes.length; i += 1) {
    const c = codes[i];
    if (c === 0) {
      return {};
    }
    if (c === 1) next.bold = true;
    if (c === 2) next.dim = true;
    if (c === 22) next.bold = false;
    if (c === 39) delete next.color;
    if (FG[c]) next.color = FG[c];
    if (c === 38 && codes[i + 1] === 5 && codes[i + 2] != null) {
      const palette = codes[i + 2];
      if (palette >= 0 && palette <= 15) {
        const base = [
          '#000000',
          '#cd3131',
          '#0dbc79',
          '#e5e510',
          '#2472c8',
          '#bc3fbc',
          '#11a8cd',
          '#e5e5e5',
          '#666666',
          '#f14c4c',
          '#23d18b',
          '#f5f543',
          '#3b8eea',
          '#d670d6',
          '#29b8db',
          '#ffffff',
        ];
        next.color = base[palette] ?? next.color;
      }
      i += 2;
    }
  }
  return next;
}

function styleToClass(state: StyleState): string {
  const parts: string[] = [];
  if (state.bold) parts.push('font-bold');
  if (state.dim) parts.push('opacity-70');
  return parts.join(' ');
}

export function ansiTextToSpans(text: string): ReactNode[] {
  if (!text) return [];
  if (!hasAnsiCodes(text)) {
    const lines = text.split('\n');
    return lines.map((line, i) => {
      const { className, text: t } = colorizePlainLogLine(line);
      return (
        <span key={`ln-${i}`} className={className}>
          {t}
          {i < lines.length - 1 ? '\n' : ''}
        </span>
      );
    });
  }
  ANSI_RE.lastIndex = 0;

  const nodes: ReactNode[] = [];
  let state: StyleState = {};
  let last = 0;
  let key = 0;
  const src = text;

  const flush = (end: number) => {
    if (end <= last) return;
    const chunk = src.slice(last, end);
    if (!chunk) return;
    const cls = styleToClass(state);
    nodes.push(
      <span
        key={`c-${key++}`}
        className={cls || undefined}
        style={state.color ? { color: state.color } : undefined}
      >
        {chunk}
      </span>
    );
    last = end;
  };

  let m: RegExpExecArray | null;
  while ((m = ANSI_RE.exec(src)) !== null) {
    flush(m.index);
    const raw = m[1] || m[2] || '';
    const codes = raw
      .split(';')
      .filter(Boolean)
      .map((x) => Number.parseInt(x, 10))
      .filter((n) => !Number.isNaN(n));
    if (codes.length === 0) codes.push(0);
    state = applyCodes(state, codes);
    last = m.index + m[0].length;
  }
  flush(src.length);
  return nodes.length ? nodes : [text];
}

export function AnsiLogText({ text, className = '' }: { text: string; className?: string }) {
  return (
    <code className={`font-mono text-xs whitespace-pre-wrap break-words ${className}`}>
      {ansiTextToSpans(text)}
    </code>
  );
}
