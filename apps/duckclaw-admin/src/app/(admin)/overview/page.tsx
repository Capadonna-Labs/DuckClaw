'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminHealth } from '@/types/admin';
import { Bot, Database, Radio } from 'lucide-react';
import { OverviewOpsPanel } from '@/components/admin/OverviewOpsPanel';
import { friendlyGatewayError } from '@/lib/adminErrors';
import {
  formatGatewayStatus,
  formatRedisStatus,
  isGatewayHealthy,
} from '@/lib/healthLabels';
import { useAuthStore } from '@/store/authStore';

export default function OverviewPage() {
  const { usuario } = useAuthStore();
  const isAdmin = usuario?.rol === 'admin';
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .health()
      .then(setHealth)
      .catch((e) =>
        setError(friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión'))
      );
  }, []);

  const reloadHealth = () => {
    setError(null);
    adminService
      .health()
      .then(setHealth)
      .catch((e) =>
        setError(friendlyGatewayError(e instanceof Error ? e.message : 'Sin conexión'))
      );
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
          Overview
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Estado del gateway, arranque de plataforma y operaciones del host
        </p>
      </header>

      {error && <GatewayErrorBanner message={error} />}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard icon={Bot} label="Workers" value={health?.workers_count ?? '—'} />
        <MetricCard
          icon={Radio}
          label="Redis"
          value={error ? 'Off-line' : formatRedisStatus(health?.redis)}
          online={error ? false : health != null ? health.redis : undefined}
        />
        <MetricCard
          icon={Database}
          label="Gateway"
          value={error ? 'Off-line' : formatGatewayStatus(health?.status)}
          online={error ? false : health != null ? isGatewayHealthy(health.status) : undefined}
        />
      </div>

      {isAdmin && (
        <OverviewOpsPanel
          gatewayStale={health != null && health.api_revision !== 2}
          onHealthReload={reloadHealth}
        />
      )}
    </div>
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

function GatewayErrorBanner({ message }: { message: string }) {
  return (
    <section className="text-sm bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-5 rounded-2xl">
      <p className="font-bold text-amber-900 dark:text-amber-200">API Gateway no disponible</p>
      <p className="text-sm text-amber-800 dark:text-amber-300 mt-1">{message}</p>
      <p className="text-sm text-amber-800/90 dark:text-amber-400/90 mt-3">
        Usa <strong>Iniciar plataforma (PM2 + Telegram)</strong> en la sección de abajo.
      </p>
    </section>
  );
}
