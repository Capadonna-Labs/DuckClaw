'use client';

/** Convierte secuencias ANSI (estilo terminal macOS/PM2) a spans coloreados. */

import type { ReactNode } from 'react';
import { useTheme } from '@/components/shared/ThemeProvider';
import { colorizePlainLogLine, hasAnsiCodes } from '@/lib/ansiLogParse';

const ANSI_RE =
  /\x1b\[([\d;]*)m|\x9b([\d;]*)m/g;

export { colorizePlainLogLine, hasAnsiCodes, stripAnsi } from '@/lib/ansiLogParse';

const FG_DARK: Record<number, string> = {
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

const FG_LIGHT: Record<number, string> = {
  30: '#475569',
  31: '#b91c1c',
  32: '#15803d',
  33: '#a16207',
  34: '#1d4ed8',
  35: '#7e22ce',
  36: '#0e7490',
  37: '#1e293b',
  90: '#64748b',
  91: '#dc2626',
  92: '#16a34a',
  93: '#ca8a04',
  94: '#2563eb',
  95: '#9333ea',
  96: '#0891b2',
  97: '#0f172a',
};

const PALETTE_DARK = [
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

const PALETTE_LIGHT = [
  '#1e293b',
  '#b91c1c',
  '#15803d',
  '#a16207',
  '#1d4ed8',
  '#7e22ce',
  '#0e7490',
  '#334155',
  '#64748b',
  '#dc2626',
  '#16a34a',
  '#ca8a04',
  '#2563eb',
  '#9333ea',
  '#0891b2',
  '#0f172a',
];

type StyleState = {
  color?: string;
  bold?: boolean;
  dim?: boolean;
};

function applyCodes(
  state: StyleState,
  codes: number[],
  fg: Record<number, string>,
  palette: string[],
): StyleState {
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
    if (fg[c]) next.color = fg[c];
    if (c === 38 && codes[i + 1] === 5 && codes[i + 2] != null) {
      const idx = codes[i + 2];
      if (idx >= 0 && idx <= 15) {
        next.color = palette[idx] ?? next.color;
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

function ansiTextToSpans(text: string, theme: 'light' | 'dark'): ReactNode[] {
  const fg = theme === 'dark' ? FG_DARK : FG_LIGHT;
  const palette = theme === 'dark' ? PALETTE_DARK : PALETTE_LIGHT;

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
      </span>,
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
    state = applyCodes(state, codes, fg, palette);
    last = m.index + m[0].length;
  }
  flush(src.length);
  return nodes.length ? nodes : [text];
}

export function AnsiLogText({ text, className = '' }: { text: string; className?: string }) {
  const { theme } = useTheme();
  return (
    <code
      className={`font-mono text-xs whitespace-pre-wrap break-words text-gov-gray-800 dark:text-slate-200 ${className}`}
    >
      {ansiTextToSpans(text, theme)}
    </code>
  );
}
