'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';
import { Radio, Square, Terminal } from 'lucide-react';

const MAX_LINES = 6_000;
const MAX_SELECTED = 2;

function sessionHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem('duckclaw-admin-auth');
    if (!raw) return {};
    const state = JSON.parse(raw)?.state;
    const headers: Record<string, string> = {};
    if (state?.usuario?.rol) headers['x-duckclaw-role'] = String(state.usuario.rol);
    if (state?.usuario?.email) headers['x-duckclaw-actor'] = String(state.usuario.email);
    return headers;
  } catch {
    return {};
  }
}

export function Pm2LiveLogsPanel() {
  const [selected, setSelected] = useState<string[]>(['DuckClaw-Gateway']);
  const [streaming, setStreaming] = useState(false);
  const [logText, setLogText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const tailRef = useRef<HTMLPreElement>(null);

  const toggle = (name: string) => {
    setSelected((prev) => {
      if (prev.includes(name)) {
        return prev.filter((x) => x !== name);
      }
      if (prev.length >= MAX_SELECTED) {
        return prev;
      }
      return [...prev, name];
    });
  };

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const start = useCallback(async () => {
    if (selected.length === 0) {
      setError('Elige 1 o 2 servicios');
      return;
    }
    stop();
    setError(null);
    setLogText('');
    setStreaming(true);

    const ac = new AbortController();
    abortRef.current = ac;

    const url = `/api/admin/ops/logs/stream?apps=${encodeURIComponent(selected.join(','))}`;

    try {
      const res = await fetch(url, {
        headers: sessionHeaders(),
        signal: ac.signal,
        cache: 'no-store',
      });

      if (!res.ok) {
        const msg = await res.text();
        try {
          const parsed = JSON.parse(msg) as { detail?: string };
          if (parsed.detail) throw new Error(parsed.detail);
        } catch (e) {
          if (e instanceof Error && e.message !== msg) throw e;
        }
        throw new Error(msg || `Error ${res.status}`);
      }
      if (!res.body) {
        throw new Error('Sin cuerpo de respuesta');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        if (lines.length === 0) continue;

        setLogText((prev) => {
          const merged =
            prev + (prev && !prev.endsWith('\n') ? '\n' : '') + lines.join('\n') + '\n';
          const all = merged.split('\n');
          if (all.length <= MAX_LINES) return merged;
          return all.slice(-MAX_LINES).join('\n');
        });
      }
    } catch (e) {
      if (ac.signal.aborted) return;
      setError(e instanceof Error ? e.message : 'Error de streaming');
    } finally {
      if (abortRef.current === ac) {
        abortRef.current = null;
        setStreaming(false);
      }
    }
  }, [selected, stop]);

  useEffect(() => {
    if (!autoScroll || !tailRef.current) return;
    tailRef.current.scrollTop = tailRef.current.scrollHeight;
  }, [logText, autoScroll]);

  useEffect(() => () => stop(), [stop]);

  return (
    <section className="mt-8 space-y-4 border-t dark:border-dark-border pt-8">
      <div className="flex items-center gap-2">
        <Terminal size={22} className="text-gov-blue-700" />
        <div>
          <h2 className="text-lg font-bold">PM2 logs en vivo</h2>
          <p className="text-sm text-gov-gray-500">
            Elige hasta 2 servicios y sigue la salida como en consola (solo en este Mac).
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {PM2_LOGGABLE_APPS.map((name) => {
          const on = selected.includes(name);
          const disabled = !on && selected.length >= MAX_SELECTED;
          return (
            <button
              key={name}
              type="button"
              disabled={streaming || disabled}
              onClick={() => toggle(name)}
              className={`px-3 py-2 rounded-xl text-sm font-semibold border transition-colors ${
                on
                  ? 'bg-gov-blue-700 text-white border-gov-blue-700'
                  : 'dark:border-dark-border hover:border-gov-blue-500 disabled:opacity-40'
              }`}
            >
              {on ? '✓ ' : ''}
              {name}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        {!streaming ? (
          <button
            type="button"
            onClick={start}
            disabled={selected.length === 0}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gov-blue-700 text-white font-semibold text-sm hover:bg-gov-blue-800 disabled:opacity-50"
          >
            <Radio size={16} />
            Iniciar stream
          </button>
        ) : (
          <button
            type="button"
            onClick={stop}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-600 text-white font-semibold text-sm hover:bg-red-700"
          >
            <Square size={16} />
            Detener
          </button>
        )}
        <button
          type="button"
          onClick={() => setLogText('')}
          className="px-3 py-2 text-sm rounded-xl border dark:border-dark-border"
        >
          Limpiar
        </button>
        <label className="flex items-center gap-2 text-sm text-gov-gray-500 ml-2">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll
        </label>
        {streaming && (
          <span className="text-xs text-emerald-600 font-semibold animate-pulse">● En vivo</span>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <pre
        ref={tailRef}
        className="p-4 text-xs font-mono bg-slate-950 text-slate-100 rounded-xl overflow-auto max-h-[min(50vh,420px)] min-h-[200px] whitespace-pre-wrap break-words"
      >
        {logText || (streaming ? 'Esperando líneas…' : 'Pulsa Iniciar stream para ver logs.')}
      </pre>
    </section>
  );
}
