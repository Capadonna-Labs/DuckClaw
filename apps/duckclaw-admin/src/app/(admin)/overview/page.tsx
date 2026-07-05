'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { OverviewMetrics } from '@/types/admin';
import { HomeChecklist } from '@/components/admin/HomeChecklist';
import { friendlyGatewayError } from '@/lib/adminErrors';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';
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
  const [metricsOpen, setMetricsOpen] = useState(false);

  useEffect(() => {
    useGatewayHealthStore
      .getState()
      .refresh()
      .then((health) => {
        if (!health) {
          setError(friendlyGatewayError('Sin conexión'));
        }
      })
      .catch((e) =>
        setError(friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión'))
      );
    if (!isAdmin) return;
    adminService
      .getOverviewMetrics()
      .then(setMetrics)
      .catch((e) =>
        setMetricsError(
          e instanceof Error ? e.message : 'No se pudieron cargar las métricas'
        )
      );
  }, [isAdmin]);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
            Inicio
          </h1>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Estado del sistema y siguiente paso claro.
          </p>
        </div>
        <Link
          href="/playground"
          className="rounded-xl bg-gov-blue-700 px-5 py-2.5 text-sm font-black text-white hover:bg-gov-blue-800"
        >
          Ir al chat
        </Link>
      </header>

      {error && <GatewayErrorBanner message={error} />}

      <HomeChecklist />

      {isAdmin && !error && (
        <section className="rounded-2xl border border-gov-gray-100 bg-white dark:border-dark-border dark:bg-dark-surface">
          <button
            type="button"
            onClick={() => setMetricsOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
            aria-expanded={metricsOpen}
          >
            <span className="text-sm font-black text-gov-gray-800 dark:text-dark-text">
              Métricas de uso (opcional)
            </span>
            <ChevronDown
              size={18}
              className={`shrink-0 transition-transform ${metricsOpen ? 'rotate-180' : ''}`}
            />
          </button>
          {metricsOpen && (
            <div className="space-y-6 border-t border-gov-gray-100 px-5 py-5 dark:border-dark-border">
              {metricsError && (
                <p className="text-sm text-amber-800 dark:text-amber-300">{metricsError}</p>
              )}
              <ChartCard title="Uso LLM — tokens y costo (USD)">
                <TokenUsageChart initial={metrics?.usage} />
              </ChartCard>
              <ChartCard title="Rendimiento">
                <ActivityChart data={metrics?.activity ?? []} />
              </ChartCard>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function GatewayErrorBanner({ message }: { message: string }) {
  return (
    <section className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-100">
      <p className="font-bold">Gateway no disponible</p>
      <p className="mt-1">{message}</p>
    </section>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-black text-gov-gray-700 dark:text-dark-muted">{title}</h3>
      <div className="min-h-[200px]">{children}</div>
    </div>
  );
}
