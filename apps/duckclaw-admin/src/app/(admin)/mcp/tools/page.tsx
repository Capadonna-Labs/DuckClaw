'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { useMcpCatalog } from '@/components/mcp/useMcpCatalog';

export default function McpToolsPage() {
  const { data, error } = useMcpCatalog();

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Herramientas DuckClaw MCP</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada a tools expuestas por el servidor DuckClaw HTTP.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && (
        <section className="overflow-x-auto rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gov-gray-500">
                <th className="pb-2">Tool</th>
                <th className="pb-2">Descripción</th>
              </tr>
            </thead>
            <tbody>
              {data.duckclaw_mcp.tools.map((tool) => (
                <tr key={tool.name} className="border-t dark:border-dark-border">
                  <td className="py-2 font-mono text-xs">{tool.name}</td>
                  <td className="py-2">{tool.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <Link href="/mcp" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a MCP
      </Link>
    </PageShell>
  );
}
