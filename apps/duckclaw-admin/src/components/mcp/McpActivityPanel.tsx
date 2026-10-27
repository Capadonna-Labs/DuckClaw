'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { McpActivity } from '@/services/admin/mcpApi';

const RANGES = [
  { days: 1, label: '24 h' },
  { days: 7, label: '7 días' },
  { days: 30, label: '30 días' },
];

function when(iso: string): string {
  const d = new Date(iso.includes('T') ? iso : `${iso.replace(' ', 'T')}Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('es-CO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function bytes(n: number): string {
  return n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`;
}

export function McpActivityPanel() {
  const [days, setDays] = useState(7);
  const [connector, setConnector] = useState('');
  const [data, setData] = useState<McpActivity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await adminService.getMcpActivity(days, connector));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar la actividad MCP');
    } finally {
      setLoading(false);
    }
  }, [days, connector]);

  useEffect(() => {
    void load();
  }, [load]);

  const connectors = Array.from(new Set((data?.summary ?? []).map((r) => r.connector_id)));
  const th = 'px-3 py-2 text-left text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted';
  const td = 'px-3 py-2 text-sm text-gov-gray-800 dark:text-dark-text';

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {RANGES.map((r) => (
          <button
            key={r.days}
            type="button"
            onClick={() => setDays(r.days)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold ${
              days === r.days
                ? 'border-gov-blue-600 bg-gov-blue-50 text-gov-blue-800 dark:border-dark-cyan dark:bg-dark-bg dark:text-dark-cyan'
                : 'border-gov-gray-200 text-gov-gray-600 dark:border-dark-border dark:text-dark-muted'
            }`}
          >
            {r.label}
          </button>
        ))}
        <select
          value={connector}
          onChange={(e) => setConnector(e.target.value)}
          aria-label="Filtrar por conector"
          className="rounded-lg border border-gov-gray-200 bg-white px-2 py-1.5 text-xs dark:border-dark-border dark:bg-dark-surface"
        >
          <option value="">Todos los conectores</option>
          {connector && !connectors.includes(connector) ? <option value={connector}>{connector}</option> : null}
          {connectors.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-bold text-gov-blue-700 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Actualizar
        </button>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {data && !data.table_ready ? (
        <p className="rounded-xl border border-dashed border-gov-gray-300 p-6 text-center text-sm text-gov-gray-500 dark:border-dark-border dark:text-dark-muted">
          Aún no hay llamadas registradas: aparecerán aquí desde la próxima vez que un worker use una herramienta MCP.
        </p>
      ) : null}

      {data?.table_ready && data.summary.length === 0 ? (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Sin llamadas en este periodo.</p>
      ) : null}

      {data && data.summary.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className={th}>Conector</th>
                <th className={th}>Herramienta</th>
                <th className={`${th} text-right`}>Llamadas</th>
                <th className={`${th} text-right`}>Errores</th>
                <th className={`${th} text-right`}>Media</th>
                <th className={th}>Última</th>
              </tr>
            </thead>
            <tbody>
              {data.summary.map((r) => (
                <tr key={`${r.connector_id}/${r.tool_name}`} className="border-t border-gov-gray-100 dark:border-dark-border">
                  <td className={`${td} font-mono text-xs`}>{r.connector_id}</td>
                  <td className={`${td} font-mono text-xs`}>{r.tool_name}</td>
                  <td className={`${td} text-right`}>{r.calls}</td>
                  <td className={`${td} text-right ${r.errors > 0 ? 'font-bold text-red-600' : ''}`}>{r.errors}</td>
                  <td className={`${td} text-right`}>{r.avg_ms} ms</td>
                  <td className={`${td} text-xs`}>{when(r.last_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {data && data.recent.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">Últimas llamadas</h3>
          <div className="max-h-[60vh] overflow-auto rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
            <table className="min-w-full">
              <thead className="sticky top-0 bg-white dark:bg-dark-surface">
                <tr>
                  <th className={th}>Hora</th>
                  <th className={th}>Herramienta</th>
                  <th className={th}>Estado</th>
                  <th className={`${th} text-right`}>Duración</th>
                  <th className={`${th} text-right`}>Envío / respuesta</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((r, i) => (
                  <tr key={`${r.created_at}-${i}`} className="border-t border-gov-gray-100 dark:border-dark-border">
                    <td className={`${td} whitespace-nowrap text-xs`}>{when(r.created_at)}</td>
                    <td className={`${td} font-mono text-xs`}>
                      {r.connector_id} · {r.tool_name}
                    </td>
                    <td className={`${td} text-xs ${r.status === 'error' ? 'font-bold text-red-600' : 'text-green-700'}`} title={r.error || undefined}>
                      {r.status === 'error' ? `error${r.error ? `: ${r.error.slice(0, 40)}` : ''}` : 'ok'}
                    </td>
                    <td className={`${td} text-right`}>{r.duration_ms} ms</td>
                    <td className={`${td} whitespace-nowrap text-right text-xs`}>
                      {bytes(r.args_bytes)} / {bytes(r.result_bytes)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
