'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { Bot } from 'lucide-react';
import { formatGatewayStatus, isGatewayHealthy } from '@/lib/healthLabels';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

function workersTooltipLabel(workers: string[]): string {
  if (workers.length === 0) return 'Sin workers activos';
  return workers.join(', ');
}

const POLL_OK_MS = 60_000;
const POLL_ERROR_MS = 30_000;

export function PlatformStatusStrip() {
  const recovering = useGatewayHealthStore((s) => s.recovering);
  const data = useGatewayHealthStore((s) => s.data);
  const error = useGatewayHealthStore((s) => s.error);
  const fetchedAt = useGatewayHealthStore((s) => s.fetchedAt);
  const refresh = useGatewayHealthStore((s) => s.refresh);

  const poll = useCallback(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const intervalMs = useMemo(() => (error ? POLL_ERROR_MS : POLL_OK_MS), [error]);
  useVisibilityAwareInterval(poll, intervalMs);

  const workers = useMemo(
    () =>
      Array.isArray(data?.workers)
        ? data.workers.map((id) => String(id).trim()).filter(Boolean)
        : [],
    [data?.workers]
  );
  const workersCount =
    typeof data?.workers_count === 'number' ? data.workers_count : workers.length || null;

  const checking = !recovering && !error && data == null && fetchedAt === 0;
  const online = !recovering && !error && data != null && isGatewayHealthy(data.status);
  const gatewayLabel = recovering
    ? 'Recuperando…'
    : checking
      ? 'Comprobando…'
      : error
        ? 'Off-line'
        : formatGatewayStatus(data?.status);
  const workersTitle = useMemo(() => workersTooltipLabel(workers), [workers]);
  const gatewayTitle = recovering
    ? 'Recuperando stack…'
    : error
      ? 'Gateway no responde'
      : `Gateway ${gatewayLabel}`;

  return (
    <div
      className="inline-flex min-h-[42px] items-stretch rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm overflow-visible shrink-0 dark:border-dark-border dark:bg-dark-bg/80"
      aria-label="Estado de la plataforma"
    >
      <span
        className={`inline-flex items-center gap-2 px-3.5 py-2.5 ${
          recovering
            ? 'text-amber-800 dark:text-amber-300'
            : checking
              ? 'text-gov-gray-600 dark:text-dark-muted'
              : online
                ? 'text-emerald-800 dark:text-emerald-300'
                : 'text-red-800 dark:text-red-300'
        }`}
        title={gatewayTitle}
        aria-label={gatewayTitle}
      >
        <span
          className={`inline-block h-3 w-3 rounded-full shrink-0 ${
            recovering
              ? 'bg-amber-500 animate-pulse'
              : checking
                ? 'bg-gov-gray-400 animate-pulse'
                : online
                  ? 'bg-emerald-500'
                  : 'bg-red-500'
          }`}
          aria-hidden
        />
        <span className="text-sm font-bold sm:text-base">{gatewayLabel}</span>
      </span>

      <span className="w-px self-stretch bg-gov-gray-200 dark:bg-dark-border" aria-hidden />

      <span
        className="group relative inline-flex items-center gap-2 px-3.5 py-2.5 text-gov-blue-800 dark:text-dark-cyan cursor-default"
        title={workersTitle}
        aria-label={
          workers.length > 0 ? `Workers activos: ${workersCount}` : 'Sin workers activos'
        }
      >
        <Bot size={18} className="shrink-0 opacity-90" aria-hidden />
        <span className="text-sm font-black tabular-nums sm:text-base">{workersCount ?? '—'}</span>
        {workers.length > 0 ? (
          <span
            role="tooltip"
            className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 hidden w-max max-w-[min(18rem,70vw)] -translate-x-1/2 rounded-lg border border-gov-gray-700 bg-gov-gray-900 px-3 py-2 text-left text-[11px] font-medium leading-snug text-white shadow-lg group-hover:block dark:border-dark-border dark:bg-[#1e1f20]"
          >
            {workersTitle}
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
