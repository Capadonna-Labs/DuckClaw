'use client';

import type { ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';

export type DeviceStatusTone = 'ok' | 'warn' | 'bad' | 'neutral';

type DeviceStatusCardProps = {
  title: string;
  subtitle?: string;
  tone: DeviceStatusTone;
  statusLabel: string;
  children?: ReactNode;
  footer?: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
  actions?: ReactNode;
};

function toneBadgeClass(tone: DeviceStatusTone): string {
  switch (tone) {
    case 'ok':
      return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200';
    case 'warn':
      return 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100';
    case 'bad':
      return 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200';
    default:
      return 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted';
  }
}

/** Card de estado genérica: badge + refresh en header, body, acciones, footer. */
export function DeviceStatusCard({
  title,
  subtitle,
  tone,
  statusLabel,
  children,
  footer,
  onRefresh,
  refreshing = false,
  actions,
}: DeviceStatusCardProps) {
  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">{title}</h2>
            {subtitle ? (
              <p className="mt-0.5 truncate text-xs text-gov-gray-500 dark:text-dark-muted">{subtitle}</p>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${toneBadgeClass(tone)}`}
            >
              {statusLabel}
            </span>
            {onRefresh ? (
              <button
                type="button"
                disabled={refreshing}
                onClick={onRefresh}
                className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
                title="Actualizar"
                aria-label="Actualizar"
              >
                <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
                <span className="hidden sm:inline">{refreshing ? 'Actualizando…' : 'Actualizar'}</span>
              </button>
            ) : null}
          </div>
        </div>
      </div>
      <div className="space-y-3 p-4">
        {children}
        {actions ? (
          <div className="border-t border-gov-gray-100 pt-3 dark:border-dark-border">{actions}</div>
        ) : null}
        {footer ? <p className="text-xs text-gov-gray-500 dark:text-dark-muted">{footer}</p> : null}
      </div>
    </section>
  );
}
