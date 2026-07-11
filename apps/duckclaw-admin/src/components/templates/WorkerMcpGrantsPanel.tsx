'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Loader2, Plug } from 'lucide-react';
import { adminService, type WorkerMcpGrantRow } from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';

type WorkerMcpGrantsPanelProps = {
  workerId: string;
  canWrite?: boolean;
  disabled?: boolean;
};

export function WorkerMcpGrantsPanel({ workerId, canWrite = true, disabled }: WorkerMcpGrantsPanelProps) {
  const [rows, setRows] = useState<WorkerMcpGrantRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyConnectorId, setBusyConnectorId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!workerId) return Promise.resolve();
    setLoading(true);
    setError(null);
    return adminService
      .getWorkerMcpGrants(workerId)
      .then((payload) => setRows(payload.connectors ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar grants MCP'))
      .finally(() => setLoading(false));
  }, [workerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleGrant = async (row: WorkerMcpGrantRow, nextGranted: boolean) => {
    if (!canWrite || disabled || busyConnectorId) return;
    setBusyConnectorId(row.connector_id);
    setError(null);
    setNotice(null);
    try {
      const result = nextGranted
        ? await adminService.grantMcpConnector(row.connector_id, workerId)
        : await adminService.revokeMcpConnectorGrant(row.connector_id, workerId);
      const polled = await pollWriteTask(result.task_id);
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'La operación no se aplicó en DB');
      }
      setNotice(
        nextGranted
          ? `Conector «${row.display_name}» autorizado para este worker.`
          : `Grant revocado para «${row.display_name}».`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo actualizar el grant');
    } finally {
      setBusyConnectorId(null);
    }
  };

  const grantedCount = rows.filter((row) => row.granted).length;

  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <p className="flex items-center gap-2 text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
          <Plug size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
          Conectores MCP
        </p>
        <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
          {grantedCount} autorizado{grantedCount === 1 ? '' : 's'} · los grants habilitan skills MCP en runtime
        </p>
      </div>

      <div className="space-y-3 px-4 py-3">
        {error ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
            {notice}
          </p>
        ) : null}

        {loading ? (
          <p className="flex items-center gap-2 text-xs text-gov-gray-500 dark:text-dark-muted">
            <Loader2 size={14} className="animate-spin" />
            Cargando conectores…
          </p>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gov-gray-200 px-3 py-4 text-center dark:border-dark-border">
            <p className="text-xs text-gov-gray-600 dark:text-dark-muted">
              No hay conectores MCP configurados.
            </p>
            <Link
              href="/mcp"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
            >
              Configurar en Integraciones MCP
              <ExternalLink size={12} />
            </Link>
          </div>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => {
              const busy = busyConnectorId === row.connector_id;
              const canToggle = canWrite && !disabled && row.enabled && (row.has_auth || row.granted);
              return (
                <li
                  key={row.connector_id}
                  className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-gov-gray-100 px-3 py-2 dark:border-dark-border"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
                      {row.display_name}
                    </p>
                    <p className="font-mono text-[10px] text-gov-gray-400">{row.connector_id}</p>
                    {!row.has_auth && !row.granted ? (
                      <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
                        Falta autenticación — configúrala en{' '}
                        <Link href="/mcp" className="font-semibold underline">
                          MCP
                        </Link>
                      </p>
                    ) : null}
                    {!row.enabled ? (
                      <p className="mt-1 text-[10px] text-gov-gray-500">Conector deshabilitado</p>
                    ) : null}
                  </div>
                  <label className="flex shrink-0 items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={row.granted}
                      disabled={!canToggle || busy}
                      onChange={(e) => void toggleGrant(row, e.target.checked)}
                    />
                    {busy ? <Loader2 size={12} className="animate-spin" /> : null}
                    <span className="text-gov-gray-600 dark:text-dark-muted">
                      {row.granted ? 'Autorizado' : 'Sin grant'}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
