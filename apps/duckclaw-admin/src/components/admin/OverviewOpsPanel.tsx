'use client';

import { useEffect, useState } from 'react';
import { AnsiLogText } from '@/lib/ansiLog';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { StackBootstrapPanel } from '@/components/admin/StackBootstrapPanel';
import { adminService, type OpsCommand } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';
import { Activity, Radio, RefreshCw } from 'lucide-react';

/** Ya cubiertos por «Iniciar plataforma». */
const HIDDEN_IN_GRID = new Set(['start_stack', 'start_telegram_ingress']);

type Props = {
  gatewayStale?: boolean;
  onHealthReload?: () => void;
};

export function OverviewOpsPanel({ gatewayStale, onHealthReload }: Props) {
  const { usuario } = useAuthStore();
  const canRun = usuario?.rol === 'admin';
  const [opsCommands, setOpsCommands] = useState<OpsCommand[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);

  useEffect(() => {
    if (!canRun) return;
    adminService
      .listOpsCommands()
      .then((r) => setOpsCommands(r.commands ?? []))
      .catch((e) =>
        setOpsError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'))
      );
  }, [canRun]);

  const run = async (opId: string) => {
    setRunning(opId);
    setOpsError(null);
    setOutput(null);
    try {
      const r = await adminService.runOps(opId);
      setOutput(
        formatOpsOutput({
          ok: r.ok,
          exit_code: r.exit_code,
          stdout: r.stdout,
          stderr: r.stderr,
          executed_via: r.executed_via,
          op_id: opId,
        })
      );
      if (opId === 'pm2_restart_gateway' && r.ok) {
        window.setTimeout(() => window.location.reload(), 2500);
      }
    } catch (e) {
      setOpsError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'));
    } finally {
      setRunning(null);
    }
  };

  const gridCommands = opsCommands.filter((c) => !HIDDEN_IN_GRID.has(c.id));

  if (!canRun) {
    return null;
  }

  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border shadow-sm overflow-hidden">
      <div className="p-6 border-b border-gov-gray-100 dark:border-dark-border bg-gradient-to-br from-gov-blue-50 via-white to-white dark:from-dark-bg dark:via-dark-surface dark:to-dark-surface">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.2em] text-gov-blue-700 dark:text-dark-cyan">
              Centro de operación
            </p>
            <h2 className="text-2xl font-black text-gov-gray-900 dark:text-dark-text mt-1">
              Operaciones y logs
            </h2>
            <p className="text-sm text-gov-gray-600 dark:text-dark-muted mt-2 max-w-2xl">
              {'Inicia la plataforma, comprueba la conexión y ejecuta acciones PM2. Las acciones dejan huella aquí y puedes seguir los logs en vivo sin salir del Overview.'}
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300">
            <Activity size={14} />
            Operación + consola
          </span>
        </div>
        {gatewayStale && (
          <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mt-4">
            Gateway en versión anterior. Usa <strong>Iniciar plataforma</strong> o reinicia
            DuckClaw-Gateway desde PM2.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] items-start gap-6 p-6">
        <div className="space-y-5">
          <div className="rounded-2xl border border-gov-gray-100 dark:border-dark-border p-4 bg-white/80 dark:bg-dark-bg/30">
            <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text mb-3">
              Arranque y conexión
            </h3>
            <StackBootstrapPanel compact onConnected={onHealthReload} />
          </div>

          <div className="rounded-2xl border border-gov-gray-100 dark:border-dark-border p-4 bg-white/80 dark:bg-dark-bg/30">
            <div className="flex items-center gap-2 mb-3">
              <RefreshCw size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
              <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">
                Acciones PM2
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 gap-3 max-h-[420px] overflow-y-auto pr-1">
              {gridCommands.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  disabled={running !== null}
                  onClick={() => void run(c.id)}
                  className="group text-left p-4 rounded-xl border dark:border-dark-border hover:border-gov-blue-500 hover:bg-gov-blue-50/50 dark:hover:bg-dark-surface disabled:opacity-50 transition-colors"
                >
                  <p className="font-bold text-sm">{c.label}</p>
                  <p className="text-[10px] font-mono text-gov-gray-500 mt-1 truncate">
                    {c.argv.join(' ')}
                  </p>
                  {running === c.id && (
                    <p className="text-xs text-gov-blue-700 dark:text-gov-blue-400 mt-2">
                      Ejecutando…
                    </p>
                  )}
                </button>
              ))}
            </div>
          </div>

          {(opsError || output) && (
            <div className="rounded-2xl border border-gov-gray-100 dark:border-dark-border p-4">
              <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text mb-3">
                Salida de la operación
              </h3>
              {opsError && (
                <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl">
                  {opsError}
                </p>
              )}
              {output && (
                <div className="p-4 bg-slate-900 rounded-xl overflow-auto max-h-96">
                  <AnsiLogText text={output} />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="self-start xl:sticky xl:top-4 rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-100 shadow-inner">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h3 className="text-sm font-black text-white flex items-center gap-2">
                <Radio size={16} className="text-emerald-400" />
                PM2 logs en vivo
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Mira Gateway, DB-Writer o Telegram mientras ejecutas acciones.
              </p>
            </div>
            <span className="text-[10px] font-black uppercase tracking-wide text-emerald-300">
              Live
            </span>
          </div>
          <Pm2LiveLogsPanel embedded />
        </div>
      </div>
    </section>
  );
}
