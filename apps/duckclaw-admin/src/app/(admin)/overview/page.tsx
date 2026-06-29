'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { OverviewMetrics } from '@/types/admin';
import { MessageCircle, PlusCircle, Users } from 'lucide-react';
import { PlatformQuickStart } from '@/components/admin/PlatformQuickStart';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

const ActivityChart = dynamic(() => import('@/components/dashboard/ActivityChart'), { ssr: false });
const TokenUsageChart = dynamic(() => import('@/components/dashboard/TokenUsageChart'), { ssr: false });

export default function OverviewPage() {
  const { usuario } = useAuthStore();
  const isAdmin = isAdminRole(usuario?.rol);
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .health()
      .catch((e) =>
        setError(friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión'))
      );
    adminService
      .getOverviewMetrics()
      .then(setMetrics)
      .catch((e) =>
        setMetricsError(
          e instanceof Error ? e.message : 'No se pudieron cargar las métricas'
        )
      );
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
          {isAdmin ? 'Overview' : 'Inicio'}
        </h1>
      </header>

      {error && <GatewayErrorBanner message={error} />}

      <PlatformQuickStart />

      {!isAdmin && <UserHomeActions />}

      {!error && (
        <>
          {metricsError && (
            <section className="text-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-4 rounded-2xl">
              <p className="text-amber-800 dark:text-amber-300">{metricsError}</p>
            </section>
          )}
          <ChartCard title="Uso LLM — tokens y costo (USD)">
            <TokenUsageChart initial={metrics?.usage} />
          </ChartCard>
          <ChartCard title="Rendimiento">
            <ActivityChart data={metrics?.activity ?? []} />
          </ChartCard>
        </>
      )}

    </div>
  );
}

function UserHomeActions() {
  return (
    <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <HomeAction
        href="/playground"
        icon={MessageCircle}
        title="Ir al chat"
        description="Elige un agente y conversa en Playground."
        primary
      />
      <HomeAction
        href="/templates"
        icon={PlusCircle}
        title="Crear agente"
        description="Nuevo asistente con herramientas base incluidas."
      />
      <HomeAction
        href="/templates"
        icon={Users}
        title="Mis agentes"
        description="Revisa agentes propios y compartidos."
      />
    </section>
  );
}

function HomeAction({
  href,
  icon: Icon,
  title,
  description,
  primary,
}: {
  href: string;
  icon: React.ElementType;
  title: string;
  description: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded-2xl border p-5 transition-colors ${
        primary
          ? 'bg-gov-blue-700 text-white border-gov-blue-700 hover:bg-gov-blue-800'
          : 'bg-white dark:bg-dark-surface border-gov-gray-100 dark:border-dark-border hover:border-gov-blue-300'
      }`}
    >
      <Icon size={22} className={primary ? 'text-white' : 'text-gov-blue-700 dark:text-dark-cyan'} />
      <p className="font-black mt-3">{title}</p>
      <p className={`text-sm mt-1 ${primary ? 'text-white/80' : 'text-gov-gray-500 dark:text-dark-muted'}`}>
        {description}
      </p>
    </Link>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gov-gray-100 dark:border-dark-border p-5">
      <p className="text-xs text-gov-gray-500 dark:text-dark-muted uppercase font-bold tracking-wider mb-4">
        {title}
      </p>
      {children}
    </div>
  );
}

function GatewayErrorBanner({ message }: { message: string }) {
  return (
    <section className="text-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-5 rounded-2xl">
      <p className="font-bold text-amber-900 dark:text-amber-200">API Gateway no disponible</p>
      <p className="text-sm text-amber-800 dark:text-amber-300 mt-1">{message}</p>
      <p className="text-sm text-amber-800/90 dark:text-amber-400/90 mt-3">
        Levanta el stack con <code className="font-mono text-xs">duckops up</code> o usa{' '}
        <strong>Reiniciar stack</strong> en la barra superior.
      </p>
    </section>
  );
}
