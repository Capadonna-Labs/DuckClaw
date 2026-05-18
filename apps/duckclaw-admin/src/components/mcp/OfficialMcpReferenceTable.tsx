'use client';

import { useCallback, useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import type { OfficialMcpReference } from '@/lib/mcpOfficialReference';

export function OfficialMcpReferenceTable({
  reference,
}: {
  reference: OfficialMcpReference;
}) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyInstall = useCallback(async (id: string, install: string) => {
    if (!install) return;
    try {
      await navigator.clipboard.writeText(install);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId(null), 1600);
    } catch {
      /* ignore */
    }
  }, []);

  if (!reference.servers.length) {
    return <p className="text-sm text-gov-gray-500 py-4">Catálogo oficial no disponible.</p>;
  }

  const repoBase = reference.source_repo.replace(/\/$/, '');

  return (
    <div className="space-y-4">
      <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
        Servidores de referencia del steering group MCP (
        <a
          href={reference.source_repo}
          target="_blank"
          rel="noopener noreferrer"
          className="text-gov-blue-700 dark:text-dark-cyan font-semibold hover:underline"
        >
          {reference.source_label}
        </a>
        ). Para más servidores publicados, usa el{' '}
        <a
          href={reference.registry_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-gov-blue-700 dark:text-dark-cyan font-semibold hover:underline"
        >
          MCP Registry
        </a>
        .
      </p>
      <div className="overflow-x-auto rounded-2xl border dark:border-dark-border max-h-[min(50vh,420px)]">
        <table className="w-full text-sm">
          <thead className="bg-gov-gray-50 dark:bg-dark-bg sticky top-0">
            <tr>
              <th className="px-3 py-2 text-left">Servidor</th>
              <th className="px-3 py-2 text-left">Descripción</th>
              <th className="px-3 py-2 text-left">Instalación</th>
              <th className="px-3 py-2 text-left w-24">Repo</th>
            </tr>
          </thead>
          <tbody>
            {reference.servers.map((s) => (
              <tr key={s.id} className="border-t dark:border-dark-border align-top">
                <td className="px-3 py-2">
                  <span className="font-semibold">{s.name}</span>
                  <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-600 dark:text-dark-muted">
                    {s.runtime}
                  </span>
                </td>
                <td className="px-3 py-2 text-gov-gray-600 dark:text-dark-muted text-xs max-w-xs">
                  {s.description}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-start gap-1 max-w-md">
                    <code className="text-[10px] font-mono break-all flex-1">{s.install}</code>
                    <button
                      type="button"
                      onClick={() => void copyInstall(s.id, s.install)}
                      className="shrink-0 p-1 rounded hover:bg-gov-gray-100 dark:hover:bg-dark-border"
                      title="Copiar comando"
                      aria-label={`Copiar instalación de ${s.name}`}
                    >
                      {copiedId === s.id ? (
                        <Check size={14} className="text-green-600" />
                      ) : (
                        <Copy size={14} />
                      )}
                    </button>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <a
                    href={`${repoBase}/tree/main/${s.repo_path}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 text-xs text-gov-blue-700 dark:text-dark-cyan font-semibold hover:underline"
                  >
                    GitHub <ExternalLink size={12} />
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
