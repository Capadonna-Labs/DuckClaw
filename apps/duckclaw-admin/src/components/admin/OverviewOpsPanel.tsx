'use client';

import { useEffect, useState } from 'react';
import { AnsiLogText } from '@/lib/ansiLog';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { StackBootstrapPanel } from '@/components/admin/StackBootstrapPanel';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';
import { adminService, type OpsCommand } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import SettingsSection from '@/components/settings/SettingsSection';
import { RefreshCw } from 'lucide-react';

/** Ya cubiertos por «Iniciar plataforma». */
const HIDDEN_IN_GRID = new Set(['start_stack', 'start_telegram_ingress']);

type Props = {
  gatewayStale?: boolean;
  onHealthReload?: () => void;
};

export function OverviewOpsPanel({ gatewayStale, onHealthReload }: Props) {
  const { usuario } = useAuthStore();
  const canRun = usuario?.rol === 'admin';
  const [commands, setCommands] = useState<OpsCommand[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canRun) return;
    adminService
      .listOpsCommands()
      .then((r) => setCommands(r.commands ?? []))
      .catch((e) =>
        setError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'))
      );
  }, [canRun]);

  const run = async (opId: string) => {
    setRunning(opId);
    setError(null);
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
      setError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'));
    } finally {
      setRunning(null);
    }
  };

  const gridCommands = commands.filter((c) => !HIDDEN_IN_GRID.has(c.id));

  if (!canRun) {
    return null;
  }

  return (
    <div className="space-y-6">
      <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 space-y-4">
        <div className="flex items-center gap-2">
          <RefreshCw size={20} className="text-gov-blue-700" />
          <h2 className="text-lg font-bold">Plataforma y operaciones</h2>
        </div>
        {gatewayStale && (
          <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl">
            Gateway en versión anterior. Usa <strong>Reiniciar DuckClaw-Gateway</strong> en la cuadrícula
            o <strong>Iniciar plataforma</strong>.
          </p>
        )}
        <StackBootstrapPanel compact onConnected={onHealthReload} />
      </section>

      <SettingsSection
        titulo="Comandos del host"
        descripcion="PM2, doctor y bootstrap en el repo DuckClaw (solo admin, auditado)"
        icono={<RefreshCw size={22} />}
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {gridCommands.map((c) => (
            <button
              key={c.id}
              type="button"
              disabled={running !== null}
              onClick={() => void run(c.id)}
              className="text-left p-4 rounded-xl border dark:border-dark-border hover:border-gov-blue-500 disabled:opacity-50 transition-colors"
            >
              <p className="font-bold text-sm">{c.label}</p>
              <p className="text-[10px] font-mono text-gov-gray-500 mt-1 truncate">
                {c.argv.join(' ')}
              </p>
              {running === c.id && (
                <p className="text-xs text-gov-blue-700 dark:text-gov-blue-400 mt-2">Ejecutando…</p>
              )}
            </button>
          ))}
        </div>
        {error && (
          <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mt-4">
            {error}
          </p>
        )}
        {output && (
          <div className="mt-4 p-4 bg-slate-900 rounded-xl overflow-auto max-h-96">
            <AnsiLogText text={output} />
          </div>
        )}
        <div className="mt-6">
          <Pm2LiveLogsPanel />
        </div>
      </SettingsSection>
    </div>
  );
}
