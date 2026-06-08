'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { McpCmdBlock } from '@/components/mcp/McpCmdBlock';
import { useMcpCatalog, useMcpLiveStatus } from '@/components/mcp/useMcpCatalog';

export default function McpServerPage() {
  const { data, error } = useMcpCatalog();
  const { live } = useMcpLiveStatus();
  const isUp = live?.reachable === true;

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Servidor DuckClaw MCP</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada al comando local y endpoint HTTP.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && <McpCmdBlock data={data} live={live} isUp={isUp} />}
      <Link href="/mcp" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a MCP
      </Link>
    </PageShell>
  );
}
