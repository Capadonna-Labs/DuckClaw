'use client';

import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';
import { useAuthStore } from '@/store/authStore';
import { Radio } from 'lucide-react';

type Props = {
  gatewayStale?: boolean;
};

export function OverviewOpsPanel({ gatewayStale }: Props) {
  const { usuario } = useAuthStore();
  const canRun = usuario?.rol === 'admin';

  if (!canRun) {
    return null;
  }

  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border shadow-sm overflow-hidden">
      <div className="p-4 sm:p-6 border-b border-gov-gray-100 dark:border-dark-border bg-gradient-to-br from-gov-blue-50 via-white to-white dark:from-dark-bg dark:via-dark-surface dark:to-dark-surface">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-black uppercase tracking-[0.2em] text-gov-blue-700 dark:text-dark-cyan">
              Observabilidad
            </p>
            <h2 className="text-xl sm:text-2xl font-black text-gov-gray-900 dark:text-dark-text mt-1">
              Logs en vivo
            </h2>
            <p className="text-sm text-gov-gray-600 dark:text-dark-muted mt-2 max-w-2xl">
              El stack se levanta con <code className="font-mono text-xs">duckops up</code> en la CLI. Aquí solo
              sigues Gateway, DB-Writer o Telegram.
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300 shrink-0">
            <Radio size={14} />
            Live
          </span>
        </div>
        {gatewayStale && (
          <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mt-4">
            Gateway en versión anterior. Reinicia el stack desde la topbar o con{' '}
            <code className="font-mono text-xs">duckops up</code>.
          </p>
        )}
      </div>

      <div className="p-4 sm:p-6">
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3 sm:p-4 text-slate-100 shadow-inner min-w-0 overflow-hidden">
          <Pm2LiveLogsPanel embedded />
        </div>
      </div>
    </section>
  );
}
