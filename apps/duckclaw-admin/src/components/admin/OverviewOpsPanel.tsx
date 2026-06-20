'use client';

import { StackBootstrapPanel } from '@/components/admin/StackBootstrapPanel';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';
import { useAuthStore } from '@/store/authStore';
import { Activity, Radio } from 'lucide-react';

type Props = {
  gatewayStale?: boolean;
  onHealthReload?: () => void;
};

export function OverviewOpsPanel({ gatewayStale, onHealthReload }: Props) {
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
              Centro de operación
            </p>
            <h2 className="text-xl sm:text-2xl font-black text-gov-gray-900 dark:text-dark-text mt-1">
              Operaciones y logs
            </h2>
            <p className="text-sm text-gov-gray-600 dark:text-dark-muted mt-2 max-w-2xl">
              Inicia la plataforma, ejecuta acciones PM2 desde la consola y sigue los logs en vivo.
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300 shrink-0">
            <Activity size={14} />
            Operación + consola
          </span>
        </div>
        {gatewayStale && (
          <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mt-4">
            Gateway en versión anterior. Usa <strong>Iniciar plataforma</strong> o reinicia
            DuckClaw-Gateway desde la consola PM2.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] items-start gap-4 sm:gap-6 p-4 sm:p-6">
        <div className="rounded-2xl border border-gov-gray-100 dark:border-dark-border p-4 bg-white/80 dark:bg-dark-bg/30 min-w-0">
          <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text mb-3">
            Arranque y conexión
          </h3>
          <StackBootstrapPanel compact onConnected={onHealthReload} />
        </div>

        <div className="self-start xl:sticky xl:top-4 rounded-2xl border border-slate-800 bg-slate-950 p-3 sm:p-4 text-slate-100 shadow-inner min-w-0 overflow-hidden">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="min-w-0">
              <h3 className="text-sm font-black text-white flex items-center gap-2">
                <Radio size={16} className="text-emerald-400 shrink-0" />
                PM2 logs en vivo
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Acciones PM2 y stream de Gateway, DB-Writer o Telegram.
              </p>
            </div>
            <span className="text-[10px] font-black uppercase tracking-wide text-emerald-300 shrink-0">
              Live
            </span>
          </div>
          <Pm2LiveLogsPanel embedded showQuickActions />
        </div>
      </div>
    </section>
  );
}
