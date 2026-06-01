'use client';

import { useCallback, useState } from 'react';
import { Check, Copy, Database } from 'lucide-react';

export type AccessTabId = 'console' | 'telegram' | 'shared';

const TABLE_ROWS: {
  id: AccessTabId;
  label: string;
  table: string;
  roleField: string;
}[] = [
  {
    id: 'console',
    label: 'Usuarios consola',
    table: 'Acceso a la consola',
    roleField: 'Admin o usuario',
  },
  {
    id: 'telegram',
    label: 'Usuarios Telegram',
    table: 'Acceso al bot',
    roleField: 'Admin o usuario',
  },
  {
    id: 'shared',
    label: 'Permisos bases compartidas',
    table: 'Bases compartidas',
    roleField: 'Permiso asignado',
  },
];

type Props = {
  dbPath?: string;
  dbExists?: boolean;
  activeTab: AccessTabId;
  tenantId?: string;
};

export function AccessPersistenceInfo({ dbPath, dbExists, activeTab, tenantId }: Props) {
  const [copied, setCopied] = useState(false);
  const path = (dbPath || '').trim();

  const copyPath = useCallback(async () => {
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }, [path]);

  return (
    <section
      className="rounded-2xl border border-gov-blue-200 dark:border-gov-blue-900/50 bg-gov-blue-50/60 dark:bg-gov-blue-950/30 p-4 space-y-3"
      aria-label="Base de datos de acceso"
    >
      <div className="flex flex-wrap items-start gap-2 justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Database size={18} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" />
          <div>
            <p className="text-sm font-bold text-gov-gray-900 dark:text-dark-text">
              Hub Gateway DuckDB
            </p>
            <p className="text-xs text-gov-gray-600 dark:text-dark-muted">
              Acceso a consola, Telegram y bases compartidas
            </p>
          </div>
        </div>
        {path && (
          <button
            type="button"
            onClick={copyPath}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border dark:border-dark-border bg-white dark:bg-dark-surface text-xs font-semibold shrink-0"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copiado' : 'Copiar ruta'}
          </button>
        )}
      </div>

      <div className="rounded-xl border dark:border-dark-border bg-white/80 dark:bg-dark-surface px-3 py-2">
        {path ? (
          <p className="text-xs font-mono text-gov-gray-800 dark:text-dark-text break-all leading-relaxed">
            {path}
          </p>
        ) : (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Ruta no resuelta — revisa <code className="font-mono">DUCKCLAW_GATEWAY_DB</code> en el
            gateway.
          </p>
        )}
        {path && dbExists === false && (
          <p className="text-xs text-red-600 mt-2">El archivo no existe en disco.</p>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border dark:border-dark-border">
        <table className="w-full text-xs">
          <thead className="bg-white/70 dark:bg-dark-bg text-left">
            <tr>
              <th className="px-3 py-2 font-semibold text-gov-gray-500">Ámbito</th>
              <th className="px-3 py-2 font-semibold text-gov-gray-500">Uso</th>
              <th className="px-3 py-2 font-semibold text-gov-gray-500 hidden sm:table-cell">
                Roles / permisos
              </th>
            </tr>
          </thead>
          <tbody>
            {TABLE_ROWS.map((row) => {
              const active = row.id === activeTab;
              return (
                <tr
                  key={row.id}
                  className={`border-t dark:border-dark-border ${
                    active
                      ? 'bg-gov-blue-100/70 dark:bg-gov-blue-900/25'
                      : 'bg-white/50 dark:bg-dark-surface/50'
                  }`}
                >
                  <td className="px-3 py-2 font-medium">{row.label}</td>
                  <td className="px-3 py-2 font-mono">{row.table}</td>
                  <td className="px-3 py-2 font-mono hidden sm:table-cell text-gov-gray-600 dark:text-dark-muted">
                    {row.id === 'telegram' && tenantId ? (
                      <>
                        {row.roleField}
                        <span className="block text-[10px] mt-0.5">Tenant: {tenantId}</span>
                      </>
                    ) : (
                      row.roleField
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
