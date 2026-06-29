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

      <section className="mt-8 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Guía rápida de prueba</h2>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-gov-gray-700 dark:text-dark-muted">
          <li>
            Reinicia el gateway: Ops → <span className="font-mono">pm2_restart_gateway</span> (o{' '}
            <span className="font-mono">pm2 restart DuckClaw-Gateway --update-env</span>).
          </li>
          <li>
            Prueba local sin token: preset <span className="font-mono">mcp_time</span> → Crear → Probar
            list_tools → Grant a un worker → Playground con ese worker.
          </li>
          <li>
            Higgsfield: cuenta en{' '}
            <a href="https://higgsfield.ai" target="_blank" rel="noreferrer" className="font-bold text-gov-blue-700 dark:text-dark-cyan">
              higgsfield.ai
            </a>
            , conecta el MCP en Claude/Cursor, captura el Bearer (DevTools) y pégalo aquí.
          </li>
          <li>
            En Playground pregunta algo que use la tool (p. ej. hora UTC con Time, o generación con Higgsfield).
          </li>
        </ol>
      </section>

      <Link href="/mcp" className="mt-6 inline-block text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        ← Volver a MCP
      </Link>
    </PageShell>
  );
}
