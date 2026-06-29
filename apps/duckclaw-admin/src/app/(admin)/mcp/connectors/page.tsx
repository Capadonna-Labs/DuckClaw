'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { McpConnectorsPanel } from '@/components/mcp/McpConnectorsPanel';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

export default function McpConnectorsPage() {
  const { usuario } = useAuthStore();
  const canWrite = isAdminRole(usuario?.rol);

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Conectores MCP</h1>
        <p className="mt-1 max-w-3xl text-sm text-gov-gray-500 dark:text-dark-muted">
          Registry DB-first: presets (Higgsfield, Fetch, Time), auth centralizado y grants por worker.
          Las tools aparecen en runtime como <span className="font-mono">mcp__&#123;connector&#125;__&#123;tool&#125;</span>.
        </p>
      </header>

      <McpConnectorsPanel canWrite={canWrite} />

      <Link href="/mcp" className="mt-6 inline-block text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        ← Volver a MCP
      </Link>
    </PageShell>
  );
}
