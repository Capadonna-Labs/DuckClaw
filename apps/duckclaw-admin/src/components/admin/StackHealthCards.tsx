'use client';

import { useCallback, useMemo, useState } from 'react';
import { Activity, Cpu, Database, Inbox, Layers, RefreshCw } from 'lucide-react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { useRelativeTimeLabel } from '@/hooks/useRelativeTimeLabel';
import { formatRedisStatus, isGatewayHealthy } from '@/lib/healthLabels';
import { isAdminRole } from '@/lib/roles';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';
import type { AdminHealth, GatewayHealthMetrics, Pm2ProcessHealth } from '@/types/admin';

const RAM_WARN_MB = 800;
const WRITE_QUEUE_WARN_DEPTH = 5;

const PM2_SUBROW_NAMES = new Set([
  'DuckClaw-DB-Writer',
  'DuckClaw-Knowledge-Indexer',
  'DuckClaw-Heartbeat',
]);

type CardTone = 'ok' | 'warn' | 'bad' | 'neutral';

type StackCard = {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: CardTone;
  icon: typeof Cpu;
  cacheEntries?: number;
  cacheEnabled?: boolean;
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
  const ragQueueDepth = metrics?.knowledge_sync_queue_depth;
  const writeQueueDepth = metrics?.db_write_queue_depth;
  const cache = metrics?.worker_graph_cache;
  const cacheEntries = cache?.entries ?? 0;
  const cacheMax = cache?.max_entries ?? 8;
  const cacheEnabled = cache?.enabled !== false;

  const ramTone: CardTone =
    typeof rss === 'number' && rss > RAM_WARN_MB ? 'warn' : typeof rss === 'number' ? 'ok' : 'neutral';
  const ragQueueTone: CardTone =
    typeof ragQueueDepth === 'number' && ragQueueDepth > 0
      ? 'warn'
      : typeof ragQueueDepth === 'number'
        ? 'ok'
        : 'neutral';
  const writeQueueTone: CardTone =
    typeof writeQueueDepth === 'number' && writeQueueDepth >= WRITE_QUEUE_WARN_DEPTH
      ? 'warn'
      : typeof writeQueueDepth === 'number' && writeQueueDepth > 0
        ? 'neutral'
        : typeof writeQueueDepth === 'number'
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
      value: typeof ragQueueDepth === 'number' ? String(ragQueueDepth) : '—',
      hint:
        typeof ragQueueDepth === 'number' && ragQueueDepth > 0
          ? 'Jobs pendientes en Redis'
          : 'Sin jobs en cola',
      tone: ragQueueTone,
      icon: Layers,
    },
    {
      id: 'write-queue',
      label: 'Cola writes',
      value: typeof writeQueueDepth === 'number' ? String(writeQueueDepth) : '—',
      hint:
        typeof writeQueueDepth === 'number' && writeQueueDepth >= WRITE_QUEUE_WARN_DEPTH
          ? 'Backlog alto — DB-Writer'
          : typeof writeQueueDepth === 'number' && writeQueueDepth > 0
            ? 'Writes admin pendientes'
            : 'DB-Writer al día',
      tone: writeQueueTone,
      icon: Inbox,
    },
    {
      id: 'worker-cache',
      label: 'Caché workers',
      value: cacheEnabled ? `${cacheEntries}/${cacheMax}` : 'off',
      hint: cacheEnabled ? 'Grafos LangGraph reutilizables' : 'Caché desactivada',
      tone: 'neutral',
      icon: Activity,
      cacheEntries,
      cacheEnabled,
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

function pm2StatusTone(status: string | undefined): CardTone {
  switch ((status || '').toLowerCase()) {
    case 'online':
      return 'ok';
    case 'stopped':
    case 'stopping':
      return 'neutral';
    case 'errored':
    case 'error':
      return 'bad';
    default:
      return 'neutral';
  }
}

function formatPm2Status(status: string | undefined): string {
  switch ((status || '').toLowerCase()) {
    case 'online':
      return 'Online';
    case 'stopped':
      return 'Detenido';
    case 'stopping':
      return 'Parando';
    case 'errored':
    case 'error':
      return 'Error';
    case 'missing':
      return 'No registrado';
    default:
      return status || '—';
  }
}

function formatPm2Memory(proc: Pm2ProcessHealth): string {
  const parts: string[] = [];
  if (typeof proc.rss_mb === 'number') {
    parts.push(`${proc.rss_mb} MB RSS`);
  }
  if (typeof proc.heap_mb === 'number') {
    parts.push(`${proc.heap_mb} MB heap`);
  }
  return parts.length > 0 ? parts.join(' · ') : '—';
}

function buildPm2SubrowProcesses(metrics: GatewayHealthMetrics | undefined): Pm2ProcessHealth[] {
  const rows = metrics?.pm2_processes ?? [];
  return rows.filter((row) => PM2_SUBROW_NAMES.has(row.name));
}

export function StackHealthCards() {
  const { usuario } = useAuthStore();
  const isAdmin = isAdminRole(usuario?.rol);
  const health = useGatewayHealthStore((s) => s.data);
  const gatewayError = useGatewayHealthStore((s) => s.error);
  const fetchedAt = useGatewayHealthStore((s) => s.fetchedAt);
  const refreshing = useGatewayHealthStore((s) => s.refreshing);
  const refresh = useGatewayHealthStore((s) => s.refresh);

  const [releaseModalOpen, setReleaseModalOpen] = useState(false);
  const [releaseBusy, setReleaseBusy] = useState(false);
  const [releaseFeedback, setReleaseFeedback] = useState<string | null>(null);

  const updatedLabel = useRelativeTimeLabel(fetchedAt);
  const cards = buildStackCards(health);
  const pm2Subrow = buildPm2SubrowProcesses(health?.gateway_metrics);
  const showPm2Subrow = pm2Subrow.length > 0;
  const workerCacheCard = cards.find((c) => c.id === 'worker-cache');
  const initialLoad = !gatewayError && health == null && fetchedAt === 0;
  const loading = initialLoad || refreshing;
  const online = health != null && isGatewayHealthy(health.status) && !gatewayError;

  const releaseModalDetails = useMemo(
    () => [
      {
        label: 'Entradas',
        value: `${workerCacheCard?.cacheEntries ?? 0} grafos en memoria`,
      },
      {
        label: 'Efecto',
        value: 'El próximo mensaje por worker reconstruye el grafo LangGraph (más latencia)',
      },
    ],
    [workerCacheCard?.cacheEntries]
  );

  const handleRefresh = useCallback(() => {
    void refresh(true);
  }, [refresh]);

  const handleConfirmRelease = useCallback(async () => {
    setReleaseBusy(true);
    setReleaseFeedback(null);
    try {
      const result = await adminService.releaseWorkerGraphCache();
      setReleaseModalOpen(false);
      const freed = Math.max(0, result.entries_before - result.entries_after);
      const rssHint =
        result.rss_mb_before != null && result.rss_mb_after != null
          ? ` RAM pico ${result.rss_mb_before}→${result.rss_mb_after} MB.`
          : '';
      setReleaseFeedback(
        freed > 0
          ? `Caché vaciada: ${freed} grafo(s) liberado(s).${rssHint}`
          : `Caché ya estaba vacía.${rssHint}`
      );
      await refresh(true);
    } catch (e) {
      setReleaseFeedback(e instanceof Error ? e.message : 'No se pudo vaciar la caché');
    } finally {
      setReleaseBusy(false);
    }
  }, [refresh]);

  return (
    <>
      <section className="rounded-2xl border border-gov-gray-100 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gov-gray-100 px-5 py-4 dark:border-dark-border">
          <div className="min-w-0">
            <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text">Estado del stack</h2>
            <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
              Gateway, colas Redis y caché LangGraph.
              {showPm2Subrow ? ' Procesos PM2 del stack debajo.' : null}
              {fetchedAt > 0 ? (
                <>
                  {' '}
                  Actualizado <span className="font-semibold tabular-nums">{updatedLabel}</span>.
                </>
              ) : null}
            </p>
            {releaseFeedback ? (
              <p className="mt-1 text-xs font-semibold text-emerald-800 dark:text-emerald-300">{releaseFeedback}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-gray-700 hover:bg-gov-gray-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-text dark:hover:bg-dark-bg"
              aria-label="Actualizar métricas del stack"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} aria-hidden />
              {refreshing ? 'Actualizando…' : 'Actualizar'}
            </button>
            <span
              className={`rounded-lg px-2.5 py-1 text-[10px] font-black uppercase tracking-wide ${
                initialLoad
                  ? 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
                  : online
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                    : 'bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300'
              }`}
            >
              {initialLoad ? 'Comprobando…' : online ? 'Operativo' : 'Atención'}
            </span>
          </div>
        </div>
        {showPm2Subrow ? (
          <div className="flex flex-wrap gap-2 border-b border-gov-gray-100 px-5 py-3 dark:border-dark-border">
            {pm2Subrow.map((proc) => {
              const tone = pm2StatusTone(proc.status);
              return (
                <div
                  key={proc.name}
                  className={`inline-flex min-w-[9.5rem] flex-col rounded-lg border px-3 py-2 ${toneClasses(tone)}`}
                >
                  <p className="text-[10px] font-black uppercase tracking-wider opacity-80">
                    {proc.label ?? proc.name}
                  </p>
                  <p className="mt-1 text-sm font-black tabular-nums">
                    {initialLoad ? '…' : formatPm2Status(proc.status)}
                  </p>
                  <p className="mt-0.5 text-[11px] opacity-80">
                    {initialLoad ? '…' : formatPm2Memory(proc)}
                  </p>
                </div>
              );
            })}
          </div>
        ) : null}
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {cards.map((card) => {
            const Icon = card.icon;
            const showRelease =
              isAdmin &&
              card.id === 'worker-cache' &&
              card.cacheEnabled !== false &&
              (card.cacheEntries ?? 0) > 0;

            return (
              <article
                key={card.id}
                className={`rounded-xl border p-4 ${toneClasses(card.tone)}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[10px] font-black uppercase tracking-wider opacity-80">{card.label}</p>
                  <Icon size={16} className="shrink-0 opacity-70" aria-hidden />
                </div>
                <p className="mt-2 text-2xl font-black tabular-nums">{initialLoad ? '…' : card.value}</p>
                <p className="mt-1 text-xs opacity-80">{card.hint}</p>
                {showRelease ? (
                  <button
                    type="button"
                    onClick={() => setReleaseModalOpen(true)}
                    className="mt-3 w-full rounded-lg border border-current/20 bg-white/40 px-2 py-1.5 text-[10px] font-black uppercase tracking-wide hover:bg-white/70 dark:bg-black/10 dark:hover:bg-black/20"
                  >
                    Vaciar caché
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>

      <ConfirmDangerModal
        isOpen={releaseModalOpen}
        title="Vaciar caché de workers"
        description="Libera grafos LangGraph en memoria del Gateway. No reinicia PM2."
        confirmLabel="Sí, vaciar caché"
        details={releaseModalDetails}
        isLoading={releaseBusy}
        onConfirm={() => void handleConfirmRelease()}
        onCancel={() => {
          if (!releaseBusy) setReleaseModalOpen(false);
        }}
      />
    </>
  );
}
