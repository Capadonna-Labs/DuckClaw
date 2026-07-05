'use client';

import { Activity, Cpu, Database, Layers } from 'lucide-react';
import type { AdminHealth, GatewayHealthMetrics } from '@/types/admin';
import { formatRedisStatus, isGatewayHealthy } from '@/lib/healthLabels';

const RAM_WARN_MB = 800;

type CardTone = 'ok' | 'warn' | 'bad' | 'neutral';

type StackCard = {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: CardTone;
  icon: typeof Cpu;
};

function toneClasses(tone: CardTone): string {
  switch (tone) {
    case 'ok':
      return 'border-emerald-200 bg-emerald-50/80 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/25 dark:text-emerald-200';
    case 'warn':
      return 'border-amber-200 bg-amber-50/80 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/25 dark:text-amber-200';
    case 'bad':
      return 'border-red-200 bg-red-50/80 text-red-900 dark:border-red-900/50 dark:bg-red-950/25 dark:text-red-200';
    default:
      return 'border-gov-gray-100 bg-white text-gov-gray-800 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text';
  }
}

function buildStackCards(health: AdminHealth | null): StackCard[] {
  const metrics: GatewayHealthMetrics | undefined = health?.gateway_metrics;
  const rss = metrics?.rss_mb;
  const queueDepth = metrics?.knowledge_sync_queue_depth;
  const cache = metrics?.worker_graph_cache;
  const cacheEntries = cache?.entries ?? 0;
  const cacheMax = cache?.max_entries ?? 8;
  const cacheEnabled = cache?.enabled !== false;

  const ramTone: CardTone =
    typeof rss === 'number' && rss > RAM_WARN_MB ? 'warn' : typeof rss === 'number' ? 'ok' : 'neutral';
  const queueTone: CardTone =
    typeof queueDepth === 'number' && queueDepth > 0
      ? 'warn'
      : typeof queueDepth === 'number'
        ? 'ok'
        : 'neutral';
  const redisTone: CardTone =
    health?.redis === true ? 'ok' : health?.redis === false ? 'bad' : 'neutral';

  return [
    {
      id: 'ram',
      label: 'Gateway RAM',
      value: typeof rss === 'number' ? `${rss} MB` : '—',
      hint: typeof rss === 'number' && rss > RAM_WARN_MB ? 'Uso elevado' : 'Proceso HTTP',
      tone: ramTone,
      icon: Cpu,
    },
    {
      id: 'rag-queue',
      label: 'Cola RAG',
      value: typeof queueDepth === 'number' ? String(queueDepth) : '—',
      hint:
        typeof queueDepth === 'number' && queueDepth > 0
          ? 'Jobs pendientes en Redis'
          : 'Sin jobs en cola',
      tone: queueTone,
      icon: Layers,
    },
    {
      id: 'worker-cache',
      label: 'Caché workers',
      value: cacheEnabled ? `${cacheEntries}/${cacheMax}` : 'off',
      hint: cacheEnabled ? 'Grafos LangGraph reutilizables' : 'Caché desactivada',
      tone: 'neutral',
      icon: Activity,
    },
    {
      id: 'redis',
      label: 'Redis',
      value: formatRedisStatus(health?.redis),
      hint: health?.redis ? 'Cola y locks OK' : 'Sin conexión',
      tone: redisTone,
      icon: Database,
    },
  ];
}

type Props = {
  health: AdminHealth | null;
  loading?: boolean;
  gatewayError?: boolean;
};

export function StackHealthCards({ health, loading, gatewayError }: Props) {
  const cards = buildStackCards(health);
  const online = health != null && isGatewayHealthy(health.status) && !gatewayError;

  return (
    <section className="rounded-2xl border border-gov-gray-100 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gov-gray-100 px-5 py-4 dark:border-dark-border">
        <div>
          <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text">Estado del stack</h2>
          <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
            Gateway, cola RAG y Redis — se actualiza con el poll del topbar.
          </p>
        </div>
        <span
          className={`rounded-lg px-2.5 py-1 text-[10px] font-black uppercase tracking-wide ${
            loading
              ? 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
              : online
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                : 'bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300'
          }`}
        >
          {loading ? 'Comprobando…' : online ? 'Operativo' : 'Atención'}
        </span>
      </div>
      <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <article
              key={card.id}
              className={`rounded-xl border p-4 ${toneClasses(card.tone)}`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-[10px] font-black uppercase tracking-wider opacity-80">{card.label}</p>
                <Icon size={16} className="shrink-0 opacity-70" aria-hidden />
              </div>
              <p className="mt-2 text-2xl font-black tabular-nums">{loading ? '…' : card.value}</p>
              <p className="mt-1 text-xs opacity-80">{card.hint}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
