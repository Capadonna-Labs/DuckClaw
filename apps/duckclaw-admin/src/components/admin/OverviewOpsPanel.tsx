'use client';

import { useEffect, useState } from 'react';
import { AnsiLogText } from '@/lib/ansiLog';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { StackBootstrapPanel } from '@/components/admin/StackBootstrapPanel';
import { adminService, type OpsCommand } from '@/services/adminService';
import type { FlyCommandEntry } from '@/types/admin';
import { useAuthStore } from '@/store/authStore';
import SettingsSection from '@/components/settings/SettingsSection';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';
import { RefreshCw, Radio, Terminal } from 'lucide-react';

/** Ya cubiertos por «Iniciar plataforma». */
const HIDDEN_IN_GRID = new Set(['start_stack', 'start_telegram_ingress']);

type Props = {
  gatewayStale?: boolean;
  onHealthReload?: () => void;
};

export function OverviewOpsPanel({ gatewayStale, onHealthReload }: Props) {
  const { usuario } = useAuthStore();
  const canRun = usuario?.rol === 'admin';
  const [flyCommands, setFlyCommands] = useState<FlyCommandEntry[]>([]);
  const [flyHeader, setFlyHeader] = useState('');
  const [copied, setCopied] = useState<string | null>(null);
  const [flyError, setFlyError] = useState<string | null>(null);
  const [opsCommands, setOpsCommands] = useState<OpsCommand[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);

  useEffect(() => {
    if (!canRun) return;
    adminService
      .listFlyCommands()
      .then((r) => {
        setFlyHeader(r.header ?? '');
        setFlyCommands(r.commands ?? []);
      })
      .catch((e) =>
        setFlyError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'))
      );
  }, [canRun]);

  useEffect(() => {
    if (!canRun) return;
    adminService
      .listOpsCommands()
      .then((r) => setOpsCommands(r.commands ?? []))
      .catch((e) =>
        setOpsError(friendlyGatewayError(e instanceof Error ? e.message : 'Error'))
      );
  }, [canRun]);

  const copyCommand = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(cmd);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

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
    <div className="space-y-6">
      <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 space-y-4">
        <div className="flex items-center gap-2">
          <RefreshCw size={20} className="text-gov-blue-700" />
          <h2 className="text-lg font-bold">Plataforma</h2>
        </div>
        {gatewayStale && (
          <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl">
            Gateway en versión anterior. Usa <strong>Iniciar plataforma</strong> o reinicia
            DuckClaw-Gateway desde PM2.
          </p>
        )}
        <StackBootstrapPanel compact onConnected={onHealthReload} />
      </section>

      <SettingsSection
        titulo="Fly Commands"
        icono={<Terminal size={22} />}
        defaultOpen={false}
      >
        {flyHeader && (
          <p className="text-sm text-gov-gray-600 dark:text-dark-muted mb-4 whitespace-pre-wrap">
            {flyHeader}
          </p>
        )}
        {flyError && (
          <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mb-4">
            {flyError}
          </p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {flyCommands.map((c) => (
            <button
              key={c.cmd}
              type="button"
              onClick={() => void copyCommand(c.cmd)}
              className="text-left p-4 rounded-xl border dark:border-dark-border hover:border-gov-blue-500 transition-colors"
            >
              <p className="font-mono text-xs text-gov-blue-700 dark:text-dark-cyan font-bold">
                {c.cmd}
              </p>
              <p className="text-sm text-gov-gray-600 dark:text-dark-muted mt-1">{c.description}</p>
              {copied === c.cmd && (
                <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-2">Copiado</p>
              )}
            </button>
          ))}
        </div>
        <p className="mt-4 text-xs text-gov-gray-500">
          Clic para copiar. Ejecuta en Telegram (admin en whitelist) o en{' '}
          <a href="/playground" className="text-gov-blue-700 dark:text-dark-cyan underline">
            Playground
          </a>
          . Referencia: <code className="font-mono">docs/COMANDOS.md</code>.
        </p>
      </SettingsSection>

      <SettingsSection
        titulo="Operaciones"
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
        {opsError && (
          <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl mt-4">
            {opsError}
          </p>
        )}
        {output && (
          <div className="mt-4 p-4 bg-slate-900 rounded-xl overflow-auto max-h-96">
            <AnsiLogText text={output} />
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        titulo="PM2 logs en vivo"
        icono={<Radio size={22} />}
        defaultOpen={false}
      >
        <Pm2LiveLogsPanel embedded />
      </SettingsSection>
    </div>
  );
}
