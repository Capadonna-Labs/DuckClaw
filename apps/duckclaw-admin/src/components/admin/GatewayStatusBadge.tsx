'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bot } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { formatGatewayStatus, isGatewayHealthy } from '@/lib/healthLabels';

function workersTooltipLabel(workers: string[]): string {
  if (workers.length === 0) return 'Sin workers activos visibles';
  return workers.join(', ');
}

export function PlatformStatusStrip() {
  const [workersCount, setWorkersCount] = useState<number | null>(null);
  const [workers, setWorkers] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const poll = () => {
      adminService
        .health()
        .then((h) => {
          setStatus(h.status);
          const list = Array.isArray(h.workers)
            ? h.workers.map((id) => String(id).trim()).filter(Boolean)
            : [];
          setWorkers(list);
          setWorkersCount(
            typeof h.workers_count === 'number' ? h.workers_count : list.length || null
          );
          setError(false);
        })
        .catch(() => {
          setError(true);
          setStatus(null);
          setWorkersCount(null);
          setWorkers([]);
        });
    };
    poll();
    const timer = window.setInterval(poll, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const online = !error && status != null && isGatewayHealthy(status);
  const gatewayLabel = error ? 'Off-line' : formatGatewayStatus(status);
  const workersTitle = useMemo(() => workersTooltipLabel(workers), [workers]);

  return (
    <div
      className="inline-flex items-stretch rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm overflow-visible shrink-0 dark:border-dark-border dark:bg-dark-bg/80"
      title="Estado de la plataforma"
    >
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-2 text-xs font-black ${
          online
            ? 'text-emerald-800 dark:text-emerald-300'
            : 'text-red-800 dark:text-red-300'
        }`}
      >
        <span
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${online ? 'bg-emerald-500' : 'bg-red-500'}`}
          aria-hidden
        />
        <span className="hidden sm:inline text-[10px] uppercase tracking-wide opacity-70">Sistema</span>
        <span>{gatewayLabel}</span>
      </span>

      <span className="w-px self-stretch bg-gov-gray-200 dark:bg-dark-border" aria-hidden />

      <span
        className="group relative inline-flex items-center gap-1.5 px-2.5 py-2 text-xs font-black text-gov-blue-800 dark:text-dark-cyan cursor-default"
        title={workersTitle}
        aria-label={workers.length > 0 ? `Workers activos: ${workersTitle}` : 'Sin workers activos'}
      >
        <Bot size={13} className="shrink-0 opacity-80" aria-hidden />
        <span className="hidden sm:inline text-[10px] uppercase tracking-wide opacity-70">Workers</span>
        <span className="tabular-nums">{workersCount ?? '—'}</span>
        {workers.length > 0 ? (
          <span
            role="tooltip"
            className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 hidden w-max max-w-[min(18rem,70vw)] -translate-x-1/2 rounded-lg border border-gov-gray-700 bg-gov-gray-900 px-3 py-2 text-left text-[11px] font-medium leading-snug text-white shadow-lg group-hover:block dark:border-dark-border dark:bg-[#1e1f20]"
          >
            <span className="mb-1 block text-[10px] font-black uppercase tracking-wide text-gov-gray-300">
              Workers activos
            </span>
            <span className="block whitespace-normal">{workersTitle}</span>
          </span>
        ) : null}
      </span>
    </div>
  );
}

/** @deprecated Usa PlatformStatusStrip */
export function GatewayStatusBadge() {
  return <PlatformStatusStrip />;
}
