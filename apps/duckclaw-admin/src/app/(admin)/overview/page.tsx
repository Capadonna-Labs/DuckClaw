'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminHealth, OverviewMetrics } from '@/types/admin';
import { Bot, Database, MessageCircle, PlusCircle, Users } from 'lucide-react';
import { OverviewOpsPanel } from '@/components/admin/OverviewOpsPanel';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { formatGatewayStatus, isGatewayHealthy } from '@/lib/healthLabels';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

const ActivityChart = dynamic(() => import('@/components/dashboard/ActivityChart'), { ssr: false });
const LatencyChart = dynamic(() => import('@/components/dashboard/LatencyChart'), { ssr: false });

export default function OverviewPage() {
  const { usuario } = useAuthStore();
  const isAdmin = isAdminRole(usuario?.rol);
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .health()
      .then(setHealth)
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

  const reloadHealth = () => {
    setError(null);
    setMetricsError(null);
    adminService
      .health()
      .then(setHealth)
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
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
          {isAdmin ? 'Overview' : 'Inicio'}
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          {isAdmin
            ? 'Estado del gateway, arranque de plataforma y comandos fly'
            : 'Crea agentes, conversa con default y retoma tus tareas recientes.'}
        </p>
      </header>

      {error && <GatewayErrorBanner message={error} />}

      {!isAdmin && <UserHomeActions />}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MetricCard icon={Bot} label="Workers" value={health?.workers_count ?? '—'} />
        <MetricCard
          icon={Database}
          label="Gateway"
          value={error ? 'Off-line' : formatGatewayStatus(health?.status)}
          online={error ? false : health != null ? isGatewayHealthy(health.status) : undefined}
        />
      </div>

      {!error && (
        <>
          {metricsError && (
            <section className="text-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-4 rounded-2xl">
              <p className="text-amber-800 dark:text-amber-300">{metricsError}</p>
            </section>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title="Pulso de Ejecución (7d)">
              <ActivityChart data={metrics?.activity ?? []} />
            </ChartCard>
            <ChartCard title="Rendimiento y Latencia (24h)">
              <LatencyChart data={metrics?.latency ?? []} />
            </ChartCard>
          </div>
        </>
      )}

      {isAdmin && (
        <OverviewOpsPanel
          gatewayStale={health != null && health.api_revision !== 2}
          onHealthReload={reloadHealth}
        />
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
        title="Hablar con default"
        description="Abre el chat y empieza con el agente base."
        primary
      />
      <HomeAction
        href="/projects/new"
        icon={PlusCircle}
        title="Crear agente"
        description="Wizard guiado sin tocar infraestructura."
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

function MetricCard({
  icon: Icon,
  label,
  value,
  online,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  online?: boolean;
}) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gov-gray-100 dark:border-dark-border p-5">
      <Icon className="text-gov-blue-600 dark:text-dark-cyan mb-2" size={22} />
      <p className="text-xs text-gov-gray-500 uppercase font-bold tracking-wider">{label}</p>
      <div className="flex items-center gap-2 mt-1">
        {online !== undefined && (
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${
              online ? 'bg-emerald-500' : 'bg-red-500'
            }`}
            aria-hidden
          />
        )}
        <p className="font-black text-2xl text-gov-gray-900 dark:text-dark-text">{value}</p>
      </div>
    </div>
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
        Usa <strong>Iniciar plataforma</strong> en la sección de abajo.
      </p>
    </section>
  );
}
