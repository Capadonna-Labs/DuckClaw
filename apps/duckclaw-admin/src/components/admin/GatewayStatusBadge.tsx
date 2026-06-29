'use client';

import { useEffect, useState } from 'react';
import { Bot } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { formatGatewayStatus, isGatewayHealthy } from '@/lib/healthLabels';

export function PlatformStatusStrip() {
  const [workersCount, setWorkersCount] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const poll = () => {
      adminService
        .health()
        .then((h) => {
          setStatus(h.status);
          setWorkersCount(typeof h.workers_count === 'number' ? h.workers_count : null);
          setError(false);
        })
        .catch(() => {
          setError(true);
          setStatus(null);
          setWorkersCount(null);
        });
    };
    poll();
    const timer = window.setInterval(poll, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const online = !error && status != null && isGatewayHealthy(status);
  const gatewayLabel = error ? 'Off-line' : formatGatewayStatus(status);

  return (
    <div
      className="inline-flex items-stretch rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm overflow-hidden shrink-0 dark:border-dark-border dark:bg-dark-bg/80"
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
        className="inline-flex items-center gap-1.5 px-2.5 py-2 text-xs font-black text-gov-blue-800 dark:text-dark-cyan"
        title="Workers registrados en el gateway"
      >
        <Bot size={13} className="shrink-0 opacity-80" aria-hidden />
        <span className="hidden sm:inline text-[10px] uppercase tracking-wide opacity-70">Workers</span>
        <span className="tabular-nums">{workersCount ?? '—'}</span>
      </span>
    </div>
  );
}

/** @deprecated Usa PlatformStatusStrip */
export function GatewayStatusBadge() {
  return <PlatformStatusStrip />;
}
