'use client';

import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import { OfficialMcpReferenceTable } from '@/components/mcp/OfficialMcpReferenceTable';
import { useMcpCatalog } from '@/components/mcp/useMcpCatalog';

export default function McpCatalogPage() {
  const { data, error } = useMcpCatalog();

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Catálogo oficial MCP</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada a referencia oficial y stdio solo lectura.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && (
        <>
          <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
            <OfficialMcpReferenceTable servers={data.official_reference.servers} />
            <div className="mt-4 flex flex-wrap gap-3 text-xs font-bold">
              <a
                href={data.official_reference.registry_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-gov-blue-700 hover:border-gov-blue-400 dark:border-dark-border dark:text-dark-cyan"
              >
                MCP Registry <ExternalLink size={14} />
              </a>
              <a
                href={data.official_reference.source_repo}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-gov-blue-700 hover:border-gov-blue-400 dark:border-dark-border dark:text-dark-cyan"
              >
                {data.official_reference.source_label} <ExternalLink size={14} />
              </a>
            </div>
          </section>

          <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
            <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
              Servidores stdio (solo lectura)
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {data.stdio_servers.map((server) => (
                <li key={server.id} className="rounded-lg bg-gov-gray-50 p-2 dark:bg-dark-bg">
                  <span className="font-mono font-bold">{server.id}</span>
                  <span className={server.enabled ? ' text-green-700' : ' text-gov-gray-500'}>
                    {' '}
                    · {server.enabled ? 'habilitado' : 'deshabilitado'}
                  </span>
                  <p className="mt-1 text-xs text-gov-gray-500">{server.note}</p>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-gov-gray-500">{data.github_note}</p>
          </section>
        </>
      )}
      <Link href="/mcp" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a MCP
      </Link>
    </PageShell>
  );
}
