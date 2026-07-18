'use client';

import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';

const STORAGE_KEY = 'duckclaw-admin-overview-logs-open';

/**
 * Terminal PM2 colapsable en Overview (Activity Stream / Progressive Disclosure).
 * Solo monta el stream mientras está abierta.
 */
export function OverviewLogsTerminal() {
  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      setOpen(sessionStorage.getItem(STORAGE_KEY) === '1');
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, open ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [open, hydrated]);

  return (
    <section
      className="rounded-2xl border border-gov-gray-100 bg-white dark:border-dark-border dark:bg-dark-surface"
      aria-labelledby="overview-logs-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gov-gray-100 px-5 py-4 dark:border-dark-border">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal size={18} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
          <div className="min-w-0">
            <h2
              id="overview-logs-heading"
              className="text-sm font-black text-gov-gray-800 dark:text-dark-text"
            >
              Terminal de logs
            </h2>
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              Stream PM2 del host (Gateway, DB-Writer, MCP…).
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="overview-logs-panel"
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-black transition-colors ${
            open
              ? 'border-gov-blue-700 bg-gov-blue-700 text-white'
              : 'border-gov-gray-200 bg-gov-gray-50 text-gov-gray-800 hover:border-gov-blue-300 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text'
          }`}
        >
          {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
          {open ? 'Ocultar' : 'Activar'}
        </button>
      </div>

      {open ? (
        <div id="overview-logs-panel" className="px-3 pb-3 pt-2 sm:px-4 sm:pb-4">
          <div className="overflow-hidden rounded-xl border border-gov-gray-200 dark:border-dark-border">
            <Pm2LiveLogsPanel embedded autoStart />
          </div>
        </div>
      ) : (
        <p className="px-5 py-3 text-xs text-gov-gray-500 dark:text-dark-muted">
          Cerrada. Actívala para seguir logs en vivo sin salir de Inicio.
        </p>
      )}
    </section>
  );
}
