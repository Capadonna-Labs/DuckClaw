'use client';

import { useCallback, useEffect, useState } from 'react';
import { Play, RefreshCw, Square, Terminal } from 'lucide-react';
import { cronsApi, type CronProcess } from '@/services/admin/cronsApi';
import { useAuthStore } from '@/store/authStore';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';

function formatUptime(pmUptime: number | null, status: string | null): string {
  if (status !== 'online' || !pmUptime) return '—';
  const ms = Date.now() - pmUptime;
  if (ms < 0) return '—';
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return `${Math.floor(ms / 1000)}s`;
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ${mins % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function StatusBadge({ status }: { status: string | null }) {
  const s = status ?? 'unknown';
  const classes =
    s === 'online'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
      : s === 'stopped'
        ? 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
        : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300';
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}>{s}</span>
  );
}

export default function CronsPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [crons, setCrons] = useState<CronProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [logsFor, setLogsFor] = useState<string | null>(null);
  const [logsText, setLogsText] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    cronsApi
      .list()
      .then((r) => setCrons(r.crons ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error cargando crons'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const reload = () => {
    setMsg(null);
    load();
  };

  const runAction = async (name: string, action: 'run' | 'stop' | 'start') => {
    if (!canWrite) return;
    setPending(name);
    setError(null);
    setMsg(null);
    try {
      const fn = action === 'run' ? cronsApi.runNow : action === 'stop' ? cronsApi.stop : cronsApi.start;
      const res = await fn(name);
      setMsg(
        res.ok
          ? `${name}: ${action === 'run' ? 'disparado' : action === 'stop' ? 'detenido' : 'iniciado'}.`
          : `${name}: falló (${res.stderr || res.stdout || 'sin detalle'}).`
      );
      setTimeout(load, 600);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error ejecutando acción');
    } finally {
      setPending(null);
    }
  };

  const openLogs = async (name: string) => {
    setLogsFor(name);
    setLogsLoading(true);
    setLogsText('');
    try {
      const res = await cronsApi.logs(name, 200);
      setLogsText([res.stdout, res.stderr].filter(Boolean).join('\n---\n') || '(sin salida)');
    } catch (e) {
      setLogsText(e instanceof Error ? e.message : 'Error cargando logs');
    } finally {
      setLogsLoading(false);
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Crons</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Procesos PM2 con horario cron — ver estado, disparar una corrida, o iniciar/detener.
            </p>
          </header>
        )}

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}
        {msg && (
          <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
            {msg}
          </p>
        )}

        <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
          <div className="flex items-center justify-between border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
            <div>
              <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                Procesos con cron_restart
              </h2>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                {loading ? (
                  'Cargando…'
                ) : (
                  <>
                    {crons.length} proceso{crons.length === 1 ? '' : 's'} detectado
                    {crons.length === 1 ? '' : 's'} vía <span className="font-mono">pm2 jlist</span>
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={reload}
              className="inline-flex items-center gap-2 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold dark:border-dark-border"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Recargar
            </button>
          </div>

          <div className="scrollbar-hide overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gov-gray-50 text-left dark:bg-dark-bg">
                <tr>
                  <th className="px-4 py-2 text-xs font-semibold">Nombre</th>
                  <th className="px-4 py-2 text-xs font-semibold">Estado</th>
                  <th className="px-4 py-2 text-xs font-semibold">Horario (cron)</th>
                  <th className="px-4 py-2 text-xs font-semibold">Uptime</th>
                  <th className="px-4 py-2 text-xs font-semibold">Reinicios</th>
                  <th className="px-4 py-2 text-xs font-semibold">Directorio</th>
                  {canWrite && <th className="px-4 py-2 text-xs font-semibold">Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td
                      colSpan={canWrite ? 7 : 6}
                      className="px-4 py-10 text-center text-sm text-gov-gray-500 dark:text-dark-muted"
                    >
                      Cargando procesos…
                    </td>
                  </tr>
                )}
                {!loading && crons.length === 0 && (
                  <tr>
                    <td
                      colSpan={canWrite ? 7 : 6}
                      className="px-4 py-10 text-center text-sm text-gov-gray-500 dark:text-dark-muted"
                    >
                      Ningún proceso PM2 en esta máquina declara un horario cron todavía.
                    </td>
                  </tr>
                )}
                {crons.map((c) => (
                  <tr key={c.name} className="border-t dark:border-dark-border">
                    <td className="px-4 py-2 font-mono text-xs">{c.name}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">{c.cron}</td>
                    <td className="px-4 py-2 text-xs text-gov-gray-500 dark:text-dark-muted">
                      {formatUptime(c.pm_uptime, c.status)}
                    </td>
                    <td className="px-4 py-2 text-xs text-gov-gray-500 dark:text-dark-muted">
                      {c.restarts ?? 0}
                    </td>
                    <td
                      className="max-w-xs truncate px-4 py-2 font-mono text-xs text-gov-gray-500 dark:text-dark-muted"
                      title={c.cwd ?? ''}
                    >
                      {c.cwd ?? '—'}
                    </td>
                    {canWrite && (
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            title="Ejecutar ahora"
                            disabled={pending === c.name}
                            onClick={() => runAction(c.name, 'run')}
                            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-xs font-medium disabled:opacity-50 dark:border-dark-border"
                          >
                            <Play size={12} />
                            Ejecutar
                          </button>
                          {c.status === 'online' ? (
                            <button
                              type="button"
                              title="Detener"
                              disabled={pending === c.name}
                              onClick={() => runAction(c.name, 'stop')}
                              className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-xs font-medium disabled:opacity-50 dark:border-dark-border"
                            >
                              <Square size={12} />
                              Detener
                            </button>
                          ) : (
                            <button
                              type="button"
                              title="Iniciar"
                              disabled={pending === c.name}
                              onClick={() => runAction(c.name, 'start')}
                              className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-xs font-medium disabled:opacity-50 dark:border-dark-border"
                            >
                              <Play size={12} />
                              Iniciar
                            </button>
                          )}
                          <button
                            type="button"
                            title="Ver logs"
                            onClick={() => openLogs(c.name)}
                            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-xs font-medium dark:border-dark-border"
                          >
                            <Terminal size={12} />
                            Logs
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {logsFor && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setLogsFor(null)}
          >
            <div
              className="max-h-[70vh] w-full max-w-2xl overflow-hidden rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
                <h3 className="font-mono text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
                  {logsFor}
                </h3>
                <button
                  type="button"
                  onClick={() => setLogsFor(null)}
                  className="text-xs text-gov-gray-500 dark:text-dark-muted"
                >
                  Cerrar
                </button>
              </div>
              <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-gov-gray-800 dark:text-dark-text">
                {logsLoading ? 'Cargando…' : logsText}
              </pre>
            </div>
          </div>
        )}
      </div>
    </ViewChrome>
  );
}
