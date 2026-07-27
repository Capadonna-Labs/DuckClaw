'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { AnsiLogText } from '@/lib/ansiLog';
import { mutationHeaders } from '@/lib/csrfClient';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';
import { Radio, Square, Terminal } from 'lucide-react';

const MAX_LINES = 6_000;

/** Contenedor con altura acotada; el viewport hace scroll dentro. */
const LOG_VIEWPORT_SHELL_CLASS =
  'flex min-h-[180px] max-h-[min(50vh,420px)] min-w-0 flex-col overflow-hidden';

const LOG_VIEWPORT_SCROLL_CLASS =
  'scrollbar-thin h-full min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain p-2 font-mono text-[10px] leading-relaxed text-gov-gray-800 sm:p-3 sm:text-[11px] dark:text-slate-200';

/** Clases compartidas para viewport PM2 con scroll interno acotado. */
export const PM2_LOG_VIEWPORT_SHELL_CLASS = LOG_VIEWPORT_SHELL_CLASS;
export const PM2_LOG_VIEWPORT_SCROLL_CLASS = LOG_VIEWPORT_SCROLL_CLASS;

function sessionHeaders(method = 'GET'): HeadersInit {
  return mutationHeaders(method);
}

type Pm2LogsContextValue = {
  selectedApp: string;
  setSelectedApp: (app: string) => void;
  runningApps: string[];
  offlineApps: string[];
  logApps: string[];
  desktopLogs: boolean;
  streaming: boolean;
  logText: string;
  error: string | null;
  autoScroll: boolean;
  setAutoScroll: (value: boolean) => void;
  start: () => Promise<void>;
  stop: () => void;
  clear: () => void;
  tailRef: RefObject<HTMLDivElement>;
};

const Pm2LogsContext = createContext<Pm2LogsContextValue | null>(null);

function usePm2LogsContext(): Pm2LogsContextValue {
  const ctx = useContext(Pm2LogsContext);
  if (!ctx) {
    throw new Error('Pm2LiveLogsProvider requerido');
  }
  return ctx;
}

type ProviderProps = {
  children: ReactNode;
  autoStart?: boolean;
};

export function Pm2LiveLogsProvider({ children, autoStart = false }: ProviderProps) {
  const [selectedApp, setSelectedApp] = useState<string>('DuckClaw-Gateway');
  const [runningApps, setRunningApps] = useState<string[]>(['DuckClaw-Gateway']);
  const [offlineApps, setOfflineApps] = useState<string[]>([]);
  const [logApps, setLogApps] = useState<string[]>([...PM2_LOGGABLE_APPS]);
  const [desktopLogs, setDesktopLogs] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [logText, setLogText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const tailRef = useRef<HTMLDivElement>(null);
  const autoStartedRef = useRef(false);

  const appendLog = useCallback((chunk: string) => {
    setLogText((prev) => {
      const merged = prev + (prev && !prev.endsWith('\n') ? '\n' : '') + chunk + '\n';
      const all = merged.split('\n');
      if (all.length <= MAX_LINES) return merged;
      return all.slice(-MAX_LINES).join('\n');
    });
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const clear = useCallback(() => setLogText(''), []);

  const start = useCallback(async () => {
    const canStream =
      runningApps.includes(selectedApp) ||
      (desktopLogs && selectedApp === 'DuckClaw-Gateway');
    if (!selectedApp || !canStream) {
      setError('Elige un servicio activo en PM2');
      return;
    }
    stop();
    setError(null);
    setLogText('');
    setStreaming(true);

    const ac = new AbortController();
    abortRef.current = ac;

    const url = `/api/admin/ops/logs/stream?apps=${encodeURIComponent(selectedApp)}`;

    try {
      const res = await fetch(url, {
        headers: sessionHeaders('GET'),
        credentials: 'include',
        signal: ac.signal,
        cache: 'no-store',
      });

      if (!res.ok) {
        const msg = (await res.text()).trim();
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

        appendLog(lines.join('\n'));
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
  }, [appendLog, desktopLogs, runningApps, selectedApp, stop]);

  useEffect(() => {
    if (!autoScroll || !tailRef.current) return;
    tailRef.current.scrollTop = tailRef.current.scrollHeight;
  }, [logText, autoScroll]);

  useEffect(() => () => stop(), [stop]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch('/api/admin/ops/logs/apps', {
          headers: sessionHeaders('GET'),
          credentials: 'include',
          cache: 'no-store',
        });
        if (cancelled) return;

        let running: string[] = [];
        let offline: string[] = [];
        let all: string[] = [...PM2_LOGGABLE_APPS];
        let mode = 'unknown';

        if (res.ok) {
          const data = (await res.json()) as {
            running?: string[];
            offline?: string[];
            all?: string[];
            mode?: string;
          };
          running = Array.isArray(data.running) ? data.running : [];
          offline = Array.isArray(data.offline) ? data.offline : [];
          all = Array.isArray(data.all) && data.all.length > 0 ? data.all : [...PM2_LOGGABLE_APPS];
          mode = typeof data.mode === 'string' ? data.mode : 'pm2';
        }

        if (!running.includes('DuckClaw-Gateway')) {
          const bootRes = await fetch('/api/admin/bootstrap/status', {
            headers: sessionHeaders('GET'),
            credentials: 'include',
            cache: 'no-store',
          });
          if (bootRes.ok) {
            const boot = (await bootRes.json()) as { gatewayReachable?: boolean };
            if (boot.gatewayReachable) {
              running = ['DuckClaw-Gateway'];
              offline = PM2_LOGGABLE_APPS.filter((name) => name !== 'DuckClaw-Gateway');
              all = ['DuckClaw-Gateway'];
              mode = 'desktop-client-fallback';
            }
          }
        }

        if (cancelled) return;

        setRunningApps(running);
        setOfflineApps(offline);
        setLogApps(all);
        setDesktopLogs(mode.startsWith('desktop'));
        if (running.length > 0) {
          setSelectedApp((prev) => (running.includes(prev) ? prev : running[0]));
        }
      } catch {
        /* keep defaults */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!autoStart || autoStartedRef.current) return;
    const canStart =
      runningApps.includes(selectedApp) ||
      (desktopLogs && selectedApp === 'DuckClaw-Gateway');
    if (!canStart) return;
    autoStartedRef.current = true;
    void start();
  }, [autoStart, desktopLogs, runningApps, selectedApp, start]);

  useEffect(() => {
    if (!autoStart) {
      autoStartedRef.current = false;
    }
  }, [autoStart]);

  const value: Pm2LogsContextValue = {
    selectedApp,
    setSelectedApp,
    runningApps,
    offlineApps,
    logApps,
    desktopLogs,
    streaming,
    logText,
    error,
    autoScroll,
    setAutoScroll,
    start,
    stop,
    clear,
    tailRef,
  };

  return <Pm2LogsContext.Provider value={value}>{children}</Pm2LogsContext.Provider>;
}

type ControlsProps = {
  variant?: 'studio' | 'dark';
};

export function Pm2LiveLogsControls({ variant = 'dark' }: ControlsProps) {
  const {
    selectedApp,
    setSelectedApp,
    runningApps,
    offlineApps,
    logApps,
    desktopLogs,
    streaming,
    error,
    autoScroll,
    setAutoScroll,
    start,
    stop,
    clear,
  } = usePm2LogsContext();

  const studio = variant === 'studio';

  return (
    <div
      className={`shrink-0 space-y-2 border-t px-2 py-2 dark:border-dark-border ${
        studio ? 'border-gov-gray-100' : 'border-slate-800/80 sm:px-3'
      }`}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <label className="sr-only" htmlFor="pm2-log-app-select">
          {desktopLogs ? 'Servicio (desktop)' : 'Servicio PM2'}
        </label>
        <select
          id="pm2-log-app-select"
          value={selectedApp}
          disabled={streaming}
          onChange={(e) => setSelectedApp(e.target.value)}
          className={
            studio
              ? 'min-w-0 flex-1 truncate rounded-lg border border-gov-gray-200 bg-gov-gray-50 px-2 py-1.5 text-[11px] font-semibold text-gov-gray-900 disabled:opacity-60 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text'
              : 'min-w-0 flex-1 truncate rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs font-semibold text-slate-100 disabled:opacity-60'
          }
        >
          {logApps.map((name) => {
            const isRunning = runningApps.includes(name);
            return (
              <option key={name} value={name} disabled={!isRunning}>
                {isRunning ? name : `${name} (offline)`}
              </option>
            );
          })}
        </select>
        {!streaming ? (
          <button
            type="button"
            onClick={() => void start()}
            disabled={!runningApps.includes(selectedApp) && !(desktopLogs && selectedApp === 'DuckClaw-Gateway')}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-gov-blue-700 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-gov-blue-800 disabled:opacity-50"
            title="Iniciar stream"
          >
            <Radio size={13} />
          </button>
        ) : (
          <button
            type="button"
            onClick={stop}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-red-600 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-red-700"
            title="Detener stream"
          >
            <Square size={13} />
          </button>
        )}
        <button
          type="button"
          onClick={clear}
          className={
            studio
              ? 'shrink-0 rounded-lg border border-gov-gray-200 px-2 py-1.5 text-[11px] text-gov-gray-600 hover:bg-gov-gray-50 dark:border-dark-border dark:text-dark-muted dark:hover:bg-dark-bg'
              : 'shrink-0 rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800'
          }
        >
          Limpiar
        </button>
      </div>
      <div
        className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] ${
          studio ? 'text-gov-gray-500 dark:text-dark-muted' : 'text-slate-400'
        }`}
      >
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll
        </label>
        {streaming ? (
          <span className="font-semibold text-emerald-600 dark:text-emerald-400 animate-pulse">
            ● En vivo
          </span>
        ) : null}
        {offlineApps.length > 0 && !desktopLogs ? (
          <span className="text-amber-700 dark:text-amber-400">
            Offline: {offlineApps.join(', ')}
          </span>
        ) : null}
        {desktopLogs ? (
          <span className="text-sky-700 dark:text-sky-400">Modo desktop (sin PM2)</span>
        ) : null}
      </div>
      {error ? (
        <p className={`text-[11px] ${studio ? 'text-red-600' : 'text-red-400'}`}>{error}</p>
      ) : null}
    </div>
  );
}

export function Pm2LiveLogsViewport({ className = '' }: { className?: string }) {
  const { logText, streaming, tailRef } = usePm2LogsContext();

  return (
    <div
      ref={tailRef}
      className={`${LOG_VIEWPORT_SCROLL_CLASS}${className ? ` ${className}` : ''}`}
    >
      {logText ? (
        <AnsiLogText text={logText} />
      ) : (
        <span className="text-gov-gray-500 dark:text-slate-500">
          {streaming ? 'Esperando líneas…' : 'Pulsa el botón de stream para empezar.'}
        </span>
      )}
    </div>
  );
}

type Props = {
  embedded?: boolean;
  autoStart?: boolean;
};

/** Panel completo (Overview u otros). Playground usa Provider + Controls + Viewport. */
export function Pm2LiveLogsPanel({ embedded = false, autoStart = false }: Props) {
  return (
    <Pm2LiveLogsProvider autoStart={autoStart}>
      {embedded ? (
        <div className="flex min-w-0 flex-col">
          <Pm2LiveLogsControls />
          <div className={LOG_VIEWPORT_SHELL_CLASS}>
            <Pm2LiveLogsViewport />
          </div>
        </div>
      ) : (
        <section className="mt-8 space-y-4 border-t dark:border-dark-border pt-8">
          <div className="flex items-center gap-2">
            <Terminal size={22} className="text-gov-blue-700" />
            <div>
              <h2 className="text-lg font-bold">PM2 logs en vivo</h2>
              <p className="text-sm text-gov-gray-500">
                Elige un servicio PM2 de este host y sigue la salida en vivo.
              </p>
            </div>
          </div>
          <div className="space-y-0 overflow-hidden rounded-xl border border-gov-gray-200 bg-white text-gov-gray-800 dark:border-dark-border dark:bg-slate-950/95 dark:text-slate-200">
            <Pm2LiveLogsControls />
            <div className={LOG_VIEWPORT_SHELL_CLASS}>
              <Pm2LiveLogsViewport />
            </div>
          </div>
        </section>
      )}
    </Pm2LiveLogsProvider>
  );
}
