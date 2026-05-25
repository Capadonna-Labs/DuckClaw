'use client';

import { useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

type Props = {
  onConnected?: () => void;
  compact?: boolean;
};

export function StackBootstrapPanel({ onConnected, compact }: Props) {
  const { usuario } = useAuthStore();
  const canRun = usuario?.rol === 'admin';
  const [running, setRunning] = useState(false);
  const [checking, setChecking] = useState(false);
  const [output, setOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startPlatform = async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setOutput(null);
    try {
      const r = await adminService.runOps('start_stack');
      setOutput(
        formatOpsOutput({
          ok: r.ok,
          exit_code: r.exit_code,
          stdout: r.stdout,
          stderr: r.stderr,
          executed_via: r.executed_via,
          op_id: 'start_stack',
        })
      );
      if (r.ok) {
        await waitForHealth(15, 2000, onConnected);
      } else {
        setError(
          'Arranque incompleto. Revisa PM2, Tailscale Funnel y setWebhook en la salida.'
        );
      }
    } catch (e) {
      setError(friendlyGatewayError(e instanceof Error ? e.message : 'Error al iniciar'));
    } finally {
      setRunning(false);
    }
  };

  const checkHealth = async () => {
    setChecking(true);
    setError(null);
    try {
      await adminService.health();
      onConnected?.();
    } catch (e) {
      setError(friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión'));
    } finally {
      setChecking(false);
    }
  };

  if (!canRun) {
    return (
      <p className="text-sm text-amber-800 dark:text-amber-200">
        Solo rol <strong>admin</strong> puede iniciar servicios en este Mac.
      </p>
    );
  }

  const busy = running || checking;

  return (
    <div className={compact ? 'space-y-3' : 'space-y-4'}>
      {!compact && (
        <p className="text-sm text-gov-gray-700 dark:text-dark-muted">
          Un solo paso: <strong>PM2</strong> (DB-Writer + Gateway), <strong>Tailscale Funnel</strong> y{' '}
          <strong>webhooks Telegram</strong> según <code className="text-xs">.env</code>.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void startPlatform()}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-bold rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          <Play size={16} />
          {running ? 'Iniciando plataforma…' : 'Iniciar plataforma'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void checkHealth()}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl border border-gov-gray-200 dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-bg disabled:opacity-50"
        >
          <RefreshCw size={16} className={checking ? 'animate-spin' : ''} />
          {checking ? 'Comprobando…' : 'Comprobar conexión'}
        </button>
      </div>
      {error && (
        <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl">
          {error}
        </p>
      )}
      {output && (
        <pre className="text-xs leading-relaxed bg-slate-900 text-slate-100 p-4 rounded-xl max-h-48 overflow-auto whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </div>
  );
}

async function waitForHealth(
  attempts: number,
  delayMs: number,
  onConnected?: () => void
) {
  for (let i = 0; i < attempts; i += 1) {
    await new Promise((r) => setTimeout(r, delayMs));
    try {
      await adminService.health();
      if (onConnected) {
        onConnected();
      } else {
        window.location.reload();
      }
      return;
    } catch {
      /* retry */
    }
  }
}
