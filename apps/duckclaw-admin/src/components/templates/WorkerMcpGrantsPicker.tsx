'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Loader2, Plug } from 'lucide-react';
import { adminService, type McpConnectorSummary } from '@/services/adminService';

type WorkerMcpGrantsPickerProps = {
  selectedConnectorIds: string[];
  onSelectionChange: (connectorIds: string[]) => void;
  disabled?: boolean;
};

export function WorkerMcpGrantsPicker({
  selectedConnectorIds,
  onSelectionChange,
  disabled,
}: WorkerMcpGrantsPickerProps) {
  const [connectors, setConnectors] = useState<McpConnectorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return adminService
      .listMcpConnectors()
      .then(setConnectors)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar conectores'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = new Set(selectedConnectorIds);

  const toggle = (connectorId: string, enabled: boolean) => {
    const next = new Set(selectedConnectorIds);
    if (enabled) {
      next.add(connectorId);
    } else {
      next.delete(connectorId);
    }
    onSelectionChange(Array.from(next));
  };

  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <p className="flex items-center gap-2 text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
          <Plug size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
          Conectores MCP (opcional)
        </p>
        <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
          Se autorizan al confirmar la creación del agente. Requiere conector con auth en{' '}
          <Link href="/plataforma?tab=mcp" className="font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan">
            Plataforma → MCP
          </Link>
          .
        </p>
      </div>

      <div className="space-y-3 px-4 py-3">
        {error ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="flex items-center gap-2 text-xs text-gov-gray-500 dark:text-dark-muted">
            <Loader2 size={14} className="animate-spin" />
            Cargando conectores…
          </p>
        ) : connectors.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gov-gray-200 px-3 py-4 text-center dark:border-dark-border">
            <p className="text-xs text-gov-gray-600 dark:text-dark-muted">No hay conectores MCP todavía.</p>
            <Link
              href="/plataforma?tab=mcp"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
            >
              Crear conector
              <ExternalLink size={12} />
            </Link>
          </div>
        ) : (
          <ul className="space-y-2">
            {connectors.map((connector) => {
              const canSelect = connector.enabled && connector.has_auth;
              const checked = selected.has(connector.connector_id);
              return (
                <li
                  key={connector.connector_id}
                  className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-gov-gray-100 px-3 py-2 dark:border-dark-border"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
                      {connector.display_name}
                    </p>
                    <p className="font-mono text-[10px] text-gov-gray-400">{connector.connector_id}</p>
                    {!connector.has_auth ? (
                      <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
                        Configura autenticación antes de autorizar
                      </p>
                    ) : null}
                  </div>
                  <label className="flex shrink-0 items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled || !canSelect}
                      onChange={(e) => toggle(connector.connector_id, e.target.checked)}
                    />
                    <span className="text-gov-gray-600 dark:text-dark-muted">
                      {checked ? 'Al crear' : 'Omitir'}
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
