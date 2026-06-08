'use client';

import { Circle, Play, RefreshCw } from 'lucide-react';
import type { McpLive } from '@/components/mcp/useMcpCatalog';

export function McpLiveBanner({
  live,
  isUp,
  canRunOps,
  opsRunning,
  onStart,
  onRestart,
  onRefresh,
}: {
  live: McpLive | null;
  isUp: boolean;
  canRunOps: boolean;
  opsRunning: string | null;
  onStart: () => void;
  onRestart: () => void;
  onRefresh: () => void;
}) {
  const busy = opsRunning !== null;

  return (
    <div
      className={`flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-start ${
        isUp
          ? 'border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30'
          : 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30'
      }`}
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <Circle
          size={12}
          className={`mt-1 shrink-0 fill-current ${isUp ? 'text-green-600' : 'text-red-500'}`}
        />
        <div className="min-w-0 space-y-1 text-sm">
          <p className="font-bold">{isUp ? 'MCP en línea' : 'MCP no detectado'}</p>
          {live && (
            <>
              <p className="break-all font-mono text-xs">{live.url}</p>
              <p className="font-mono text-[10px] text-gov-gray-600 dark:text-dark-muted">
                {live.command}
              </p>
              {!isUp && live.error && (
                <p className="text-xs text-red-700 dark:text-red-400">{live.error}</p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap gap-2">
        {canRunOps && (
          <>
            {!isUp && (
              <button
                type="button"
                disabled={busy}
                onClick={onStart}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-gov-blue-800 disabled:opacity-50"
              >
                <Play size={14} />
                {opsRunning === 'pm2_start_mcp' ? 'Iniciando...' : 'Iniciar MCP (PM2)'}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={onRestart}
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold hover:border-gov-blue-500 disabled:opacity-50 dark:border-dark-border"
            >
              <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
              {opsRunning === 'pm2_restart_mcp' ? 'Reiniciando...' : 'Reiniciar MCP'}
            </button>
          </>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={onRefresh}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs text-gov-gray-600 hover:bg-black/5 disabled:opacity-50 dark:hover:bg-white/5"
        >
          <RefreshCw size={14} />
          Comprobar
        </button>
      </div>
    </div>
  );
}
