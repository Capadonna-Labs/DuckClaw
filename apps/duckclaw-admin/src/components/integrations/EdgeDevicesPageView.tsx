'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { formatOpsOutput } from '@/lib/formatOpsOutput';

const STREAMLIT_URL = 'http://127.0.0.1:8501';

export default function EdgeDevicesPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [opsBusy, setOpsBusy] = useState<string | null>(null);
  const [opsOutput, setOpsOutput] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [streamlitOnline, setStreamlitOnline] = useState<boolean | null>(null);

  const checkStreamlit = useCallback(async () => {
    try {
      const res = await fetch(STREAMLIT_URL, { method: 'GET', cache: 'no-store' });
      setStreamlitOnline(res.ok);
    } catch {
      setStreamlitOnline(false);
    }
  }, []);

  useEffect(() => {
    void checkStreamlit();
  }, [checkStreamlit]);

  const runOp = async (opId: string) => {
    if (!canWrite) return;
    setOpsBusy(opId);
    setOpsError(null);
    setOpsOutput(null);
    try {
      const out = await adminService.runOps(opId);
      setOpsOutput(
        formatOpsOutput({
          ok: out.ok,
          exit_code: out.exit_code,
          stdout: out.stdout,
          stderr: out.stderr,
          executed_via: out.executed_via,
          op_id: opId,
        })
      );
      if (out.exit_code !== 0) {
        setOpsError(out.stderr || out.stdout || `Ops ${opId} falló`);
      }
      if (opId.includes('streamlit')) {
        setTimeout(() => void checkStreamlit(), 2500);
      }
    } catch (e) {
      setOpsError(e instanceof Error ? e.message : 'Error ejecutando operación');
    } finally {
      setOpsBusy(null);
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Edge devices</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Telemetría de hardware vía libedgecore
            </p>
          </header>
        )}

        <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
          Streamlit es un panel local para ver telemetría del sensor (CPU, frames seriales, estado del
          dispositivo). No forma parte del admin Next.js: corre en el puerto 8501 y usa la librería nativa{' '}
          <code className="font-mono text-xs">libedgecore</code> que debes compilar una vez en tu máquina.
        </p>

        {(opsError || opsOutput) && (
          <div className="space-y-2">
            {opsError && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
                {opsError}
              </p>
            )}
            {opsOutput && (
              <pre className="max-h-48 overflow-auto rounded-lg bg-gov-gray-50 p-3 font-mono text-xs dark:bg-dark-bg">
                {opsOutput}
              </pre>
            )}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
            <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                    Dashboard Streamlit
                  </h2>
                  <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                    UI local en {STREAMLIT_URL}
                  </p>
                </div>
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    streamlitOnline
                      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                      : streamlitOnline === false
                        ? 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100'
                        : 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
                  }`}
                >
                  {streamlitOnline === null ? 'Comprobando…' : streamlitOnline ? 'Online' : 'Offline'}
                </span>
              </div>
            </div>
            <div className="space-y-3 p-4">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={!canWrite || opsBusy !== null}
                  onClick={() => void runOp('pm2_start_edge_streamlit')}
                  className="rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {opsBusy === 'pm2_start_edge_streamlit' ? 'Iniciando…' : 'Iniciar dashboard'}
                </button>
                <button
                  type="button"
                  disabled={!canWrite || opsBusy !== null}
                  onClick={() => void runOp('pm2_restart_edge_streamlit')}
                  className="rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
                >
                  {opsBusy === 'pm2_restart_edge_streamlit' ? 'Reiniciando…' : 'Reiniciar'}
                </button>
                <button
                  type="button"
                  disabled={opsBusy !== null}
                  onClick={() => void checkStreamlit()}
                  className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold dark:border-dark-border"
                >
                  <RefreshCw size={12} />
                  Estado
                </button>
              </div>
              <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                Abrir{' '}
                <a
                  href={STREAMLIT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-gov-blue-700 dark:text-dark-cyan"
                >
                  {STREAMLIT_URL}
                  <ExternalLink size={12} />
                </a>
                {' · '}
                Docs: integrations/edge-devices/EDGE_DEVICES_STREAMLIT.md
              </p>
            </div>
          </section>

          <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
            <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
              <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                Compilar librería nativa
              </h2>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                libedgecore no va en git — compila tras cada pull
              </p>
            </div>
            <div className="space-y-3 p-4">
              <button
                type="button"
                disabled={!canWrite || opsBusy !== null}
                onClick={() => void runOp('build_edge_native')}
                className="rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                {opsBusy === 'build_edge_native' ? 'Compilando…' : 'Compilar libedgecore'}
              </button>
              <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                Genera <code className="font-mono">native/libedgecore.so</code> (Linux) o{' '}
                <code className="font-mono">.dylib</code> (macOS). Opcional:{' '}
                <code className="font-mono">DUCKCLAW_EDGE_LIB_PATH</code>
              </p>
            </div>
          </section>
        </div>
      </div>
    </ViewChrome>
  );
}
