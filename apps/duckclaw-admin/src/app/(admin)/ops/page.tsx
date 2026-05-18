'use client';

import { useEffect, useState } from 'react';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { adminService, type OpsCommand } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { Pm2LiveLogsPanel } from '@/components/admin/Pm2LiveLogsPanel';

export default function OpsPage() {
  const { usuario } = useAuthStore();
  const router = useRouter();
  const canRun = usuario?.rol === 'admin';
  const [commands, setCommands] = useState<OpsCommand[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (usuario?.rol !== 'admin') {
      router.replace('/overview');
      return;
    }
    adminService
      .listOpsCommands()
      .then((r) => setCommands(r.commands ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [usuario?.rol, router]);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setRunning(null);
    }
  };

  if (usuario?.rol !== 'admin') return null;

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Operaciones</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Comandos allowlist (PM2, doctor, bootstrap). Solo rol admin. Se registran en auditoría.
        </p>
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <SettingsSection
        titulo="Servicios y diagnóstico"
        descripcion="Ejecuta en el host donde corre el gateway (repo DuckClaw)"
        icono={<RefreshCw size={22} />}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {commands.map((c) => (
            <button
              key={c.id}
              type="button"
              disabled={!canRun || running !== null}
              onClick={() => run(c.id)}
              className="text-left p-4 rounded-xl border dark:border-dark-border hover:border-gov-blue-500 disabled:opacity-50 transition-colors"
            >
              <p className="font-bold text-sm">{c.label}</p>
              <p className="text-[10px] font-mono text-gov-gray-500 mt-1 truncate">
                {c.argv.join(' ')}
              </p>
              {running === c.id && (
                <p className="text-xs text-gov-blue-700 mt-2">Ejecutando…</p>
              )}
            </button>
          ))}
        </div>

        {output && (
          <pre className="mt-6 p-4 text-xs font-mono bg-slate-900 text-slate-100 rounded-xl overflow-x-auto max-h-96 whitespace-pre-wrap">
            {output}
          </pre>
        )}

        <Pm2LiveLogsPanel />
      </SettingsSection>
    </PageShell>
  );
}
