'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import type { McpCatalog } from '@/components/mcp/useMcpCatalog';

export function OfficialMcpReferenceTable({
  servers,
}: {
  servers: McpCatalog['official_reference']['servers'];
}) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyInstall = async (id: string, install: string) => {
    if (!install) return;
    await navigator.clipboard.writeText(install);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId(null), 1500);
  };

  if (servers.length === 0) {
    return <p className="py-4 text-sm text-gov-gray-500">Sin servidores oficiales cargados.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-2xl border dark:border-dark-border">
      <table className="w-full text-sm">
        <thead className="bg-gov-gray-50 text-left text-gov-gray-500 dark:bg-dark-bg">
          <tr>
            <th className="px-3 py-2">Servidor</th>
            <th className="px-3 py-2">Runtime</th>
            <th className="px-3 py-2">Install</th>
            <th className="px-3 py-2">Repo</th>
          </tr>
        </thead>
        <tbody>
          {servers.map((server) => (
            <tr key={server.id} className="border-t dark:border-dark-border">
              <td className="px-3 py-3 align-top">
                <p className="font-black text-gov-gray-900 dark:text-dark-text">{server.name}</p>
                <p className="mt-1 max-w-sm text-xs text-gov-gray-500 dark:text-dark-muted">
                  {server.description}
                </p>
              </td>
              <td className="px-3 py-3 align-top">
                <span className="rounded-lg bg-gov-gray-50 px-2 py-1 font-mono text-xs dark:bg-dark-bg">
                  {server.runtime}
                </span>
              </td>
              <td className="px-3 py-3 align-top">
                <div className="flex items-start gap-2">
                  <code className="block max-w-md rounded-lg bg-slate-950 px-3 py-2 text-[11px] text-slate-100">
                    {server.install}
                  </code>
                  <button
                    type="button"
                    onClick={() => void copyInstall(server.id, server.install)}
                    className="rounded-lg border p-2 text-gov-gray-500 hover:border-gov-blue-300 hover:text-gov-blue-700 dark:border-dark-border"
                    aria-label={`Copiar install ${server.name}`}
                  >
                    {copiedId === server.id ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </td>
              <td className="px-3 py-3 align-top font-mono text-xs text-gov-gray-500">
                {server.repo_path}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
