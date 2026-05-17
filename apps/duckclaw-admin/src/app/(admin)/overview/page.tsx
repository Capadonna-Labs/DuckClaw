'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminHealth } from '@/types/admin';
import { Bot, Database, Radio } from 'lucide-react';
import Link from 'next/link';
import { DiagnosticsPanel } from '@/components/admin/DiagnosticsPanel';
import { formatGatewayStatus, formatRedisStatus } from '@/lib/healthLabels';

export default function OverviewPage() {
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .health()
      .then(setHealth)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
          Overview
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Estado del gateway y servicios
        </p>
      </header>

      {error && <GatewayErrorBanner message={error} />}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard icon={Bot} label="Workers" value={health?.workers_count ?? '—'} />
        <MetricCard icon={Radio} label="Redis" value={formatRedisStatus(health?.redis)} />
        <MetricCard icon={Database} label="Gateway" value={formatGatewayStatus(health?.status)} />
      </div>

      <DiagnosticsPanel gatewayStale={health != null && health.api_revision !== 2} />

      <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6">
        <h2 className="text-lg font-bold mb-4">Accesos rápidos</h2>
        <div className="flex flex-wrap gap-3">
          <QuickLink href="/kanban" label="Tablero" />
          <QuickLink href="/projects/new" label="Crear agente" />
          <QuickLink href="/templates" label="Plantillas" />
          <QuickLink href="/telegram" label="Telegram" />
          <QuickLink href="/commands" label="Fly commands" />
          <QuickLink href="/mcp" label="MCP" />
          <QuickLink href="/skills" label="Skills" />
          <QuickLink href="/ops" label="Operaciones" />
          <QuickLink href="/traces" label="Traces" />
          <QuickLink href="/audit" label="Auditoría" />
        </div>
      </section>

      {health?.workers && health.workers.length > 0 && (
        <section className="bg-white dark:bg-dark-surface rounded-3xl border p-6 dark:border-dark-border">
          <h2 className="text-lg font-bold mb-3">Workers detectados</h2>
          <ul className="flex flex-wrap gap-2">
            {health.workers.map((w) => (
              <li key={w}>
                <Link
                  href={`/templates/${w}`}
                  className="text-xs font-mono px-2 py-1 bg-gov-gray-50 dark:bg-dark-bg rounded-lg hover:bg-gov-blue-50"
                >
                  {w}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
}) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gov-gray-100 dark:border-dark-border p-5">
      <Icon className="text-gov-blue-600 dark:text-dark-cyan mb-2" size={22} />
      <p className="text-xs text-gov-gray-500 uppercase font-bold tracking-wider">{label}</p>
      <p className="font-black text-2xl text-gov-gray-900 dark:text-dark-text mt-1">{value}</p>
    </div>
  );
}

function GatewayErrorBanner({ message }: { message: string }) {
  const isTailscale = message.includes('Tailscale');
  const isAdminKey = message.toLowerCase().includes('admin');
  return (
    <ErrorBanner>
      <p className="font-bold text-red-800 dark:text-red-300">No se pudo conectar al API Gateway</p>
      <p className="text-sm text-red-700 dark:text-red-400 mt-1">{message}</p>
      <ul className="text-sm text-red-700/90 dark:text-red-400/90 mt-3 list-disc pl-5 space-y-1">
        <li>Levanta: Redis, DuckClaw-DB-Writer, DuckClaw-Gateway (puerto 8000).</li>
        <li>
          <code className="text-xs">apps/duckclaw-admin/.env.local</code>:{' '}
          <code>DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000</code> (local, no URL Tailscale).
        </li>
        <li>
          Misma <code>DUCKCLAW_ADMIN_API_KEY</code> en .env raíz y en .env.local del admin.
        </li>
        {isTailscale && (
          <li>
            Rutas <code>/api/v1/admin/*</code> ya no exigen Tailscale; reinicia el gateway tras
            actualizar.
          </li>
        )}
        {isAdminKey && <li>Revisa que el gateway tenga definida DUCKCLAW_ADMIN_API_KEY.</li>}
      </ul>
    </ErrorBanner>
  );
}

function ErrorBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-sm bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 p-4 rounded-xl">
      {children}
    </div>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="px-4 py-2 bg-gov-blue-700 text-white text-sm font-semibold rounded-xl hover:bg-gov-blue-800"
    >
      {label}
    </Link>
  );
}
