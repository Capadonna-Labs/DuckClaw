'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { adminService, type OpsCommand } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { RefreshCw } from 'lucide-react';

const QUICK_OPS = ['pm2_list', 'doctor', 'pm2_restart_gateway', 'bootstrap_dbs'] as const;

export function DiagnosticsPanel({ gatewayStale }: { gatewayStale?: boolean }) {
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
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
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
        setError(null);
        window.setTimeout(() => window.location.reload(), 2500);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setRunning(null);
    }
  };

  const quick = commands.filter((c) =>
    (QUICK_OPS as readonly string[]).includes(c.id)
  );

  if (!canRun) {
    return (
      <p className="text-sm text-gov-gray-500">
        Diagnóstico operativo: solo rol <strong>admin</strong>.{' '}
        <Link href="/ops" className="text-gov-blue-700 font-semibold">
          Ver Operaciones
        </Link>
      </p>
    );
  }

  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 space-y-4">
      <div className="flex items-center gap-2">
        <RefreshCw size={20} className="text-gov-blue-700" />
        <h2 className="text-lg font-bold">Diagnóstico del sistema</h2>
      </div>
      {gatewayStale && (
        <p className="text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl">
          El servicio principal está en una versión anterior. Pulsa{' '}
          <strong>Reiniciar DuckClaw-Gateway</strong> (se ejecuta en este equipo aunque el gateway
          aún no tenga la ruta nueva). La página se recargará sola si el reinicio tiene éxito.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {quick.map((c) => (
          <button
            key={c.id}
            type="button"
            disabled={running !== null}
            onClick={() => run(c.id)}
            className="px-3 py-2 text-sm font-semibold rounded-xl bg-gov-blue-700 text-white hover:bg-gov-blue-800 disabled:opacity-50"
          >
            {running === c.id ? 'Ejecutando…' : c.label}
          </button>
        ))}
        <Link
          href="/ops"
          className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border self-center"
        >
          Todas las operaciones →
        </Link>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {output && (
        <pre className="text-sm leading-relaxed bg-slate-900 text-slate-100 p-4 rounded-xl max-h-64 overflow-auto whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </section>
  );
}
