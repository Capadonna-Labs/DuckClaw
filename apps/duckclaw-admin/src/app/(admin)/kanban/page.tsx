'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import type { KanbanCard, KanbanStatus } from '@/lib/kanbanTypes';
import {
  KANBAN_COLUMNS,
  KANBAN_WORKER_FILTER_KEY,
  coerceKanbanWorkerId,
  isSwarmAutoSyncCard,
} from '@/lib/kanbanTypes';
import { useAuthStore } from '@/store/authStore';
import { PageShell } from '@/components/admin/PageShell';
import { Plus, RefreshCw, GripVertical } from 'lucide-react';

function readWorkerFilter(): string {
  if (typeof window === 'undefined') return '';
  return sessionStorage.getItem(KANBAN_WORKER_FILTER_KEY) || '';
}

function sortSwarmCards(a: KanbanCard, b: KanbanCard): number {
  const wa = coerceKanbanWorkerId(a.worker_id) ?? '';
  const wb = coerceKanbanWorkerId(b.worker_id) ?? '';
  if (wa !== wb) return wa.localeCompare(wb);
  return (a.swarm_slot ?? 99) - (b.swarm_slot ?? 99);
}

function cardMatchesWorkerFilter(card: KanbanCard, filter: string): boolean {
  if (!filter) return true;
  if (isSwarmAutoSyncCard(card)) return coerceKanbanWorkerId(card.worker_id) === filter;
  return false;
}

async function fetchTeamWorkerIds(): Promise<string[]> {
  const config = await adminService.getPlaygroundConfig();
  return (config.workers ?? []).map((worker) => worker.id).filter(Boolean);
}

export default function KanbanPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [cards, setCards] = useState<KanbanCard[]>([]);
  const [teamWorkers, setTeamWorkers] = useState<string[]>([]);
  const [workerFilter, setWorkerFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setWorkerFilter(readWorkerFilter());
    fetchTeamWorkerIds().then(setTeamWorkers).catch(() => setTeamWorkers([]));
  }, []);

  const onWorkerFilterChange = (value: string) => {
    setWorkerFilter(value);
    if (typeof window !== 'undefined') {
      if (value) sessionStorage.setItem(KANBAN_WORKER_FILTER_KEY, value);
      else sessionStorage.removeItem(KANBAN_WORKER_FILTER_KEY);
    }
  };

  const load = useCallback(() => {
    setLoading(true);
    adminService
      .getKanbanCards()
      .then((r) => {
        setCards(r.cards ?? []);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const filteredCards = useMemo(() => {
    const list = cards.filter((c) => cardMatchesWorkerFilter(c, workerFilter));
    return [...list].sort(sortSwarmCards);
  }, [cards, workerFilter]);

  const workerOptions = useMemo(() => {
    const fromTeam = teamWorkers.length > 0 ? teamWorkers : [];
    const fromCards = cards
      .map((c) => c.worker_id)
      .map(coerceKanbanWorkerId)
      .filter((workerId): workerId is string => Boolean(workerId));
    return Array.from(new Set([...fromTeam, ...fromCards])).sort();
  }, [teamWorkers, cards]);

  const moveCard = async (id: string, status: KanbanStatus) => {
    if (!canWrite) return;
    const prev = cards;
    setCards((c) => c.map((x) => (x.id === id ? { ...x, status } : x)));
    try {
      await adminService.updateKanbanCard({ id, status });
    } catch (e) {
      setCards(prev);
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const addCard = async () => {
    if (!canWrite) return;
    const title = window.prompt('Nombre del agente o tarea');
    if (!title?.trim()) return;
    try {
      await adminService.createKanbanCard({
        title: title.trim(),
        status: 'pendiente',
        description: 'Creado desde el tablero',
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <PageShell>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text">Tablero de agentes</h1>
          <p className="text-sm text-gov-gray-500 mt-1 max-w-xl">
            Coordina las actividades del equipo. Instancia 1 por worker; slots 2..n cuando hay
            ejecuciones paralelas.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gov-gray-500 whitespace-nowrap">Filtrar por agente</span>
            <select
              value={workerFilter}
              onChange={(e) => onWorkerFilterChange(e.target.value)}
              className="px-2 py-2 text-sm border rounded-xl dark:border-dark-border bg-white dark:bg-dark-surface min-w-[10rem]"
            >
              <option value="">Todos</option>
              {workerOptions.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={load}
            className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border flex items-center gap-2"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          {canWrite && (
            <>
              <button
                type="button"
                onClick={addCard}
                className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border flex items-center gap-2"
              >
                <Plus size={16} /> Nueva tarjeta
              </button>
              <Link
                href="/projects/new"
                className="px-4 py-2 text-sm font-bold bg-gov-blue-700 text-white rounded-xl"
              >
                Crear agente
              </Link>
            </>
          )}
        </div>
      </header>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 min-h-[420px]">
        {KANBAN_COLUMNS.map((col) => {
          const allInCol = cards.filter((c) => c.status === col.id);
          const visible = filteredCards.filter((c) => c.status === col.id);
          return (
            <KanbanColumn
              key={col.id}
              column={col}
              cards={visible}
              totalCount={allInCol.length}
              filtered={Boolean(workerFilter)}
              filterLabel={workerFilter}
              canWrite={canWrite}
              onMove={moveCard}
            />
          );
        })}
      </div>
    </PageShell>
  );
}

function KanbanColumn({
  column,
  cards,
  totalCount,
  filtered,
  filterLabel,
  canWrite,
  onMove,
}: {
  column: (typeof KANBAN_COLUMNS)[number];
  cards: KanbanCard[];
  totalCount: number;
  filtered: boolean;
  filterLabel: string;
  canWrite: boolean;
  onMove: (id: string, status: KanbanStatus) => void;
}) {
  const order: KanbanStatus[] = ['pendiente', 'en_progreso', 'completo'];
  const idx = order.indexOf(column.id);
  const countLabel =
    filtered && totalCount !== cards.length ? `${cards.length} / ${totalCount}` : String(cards.length);

  return (
    <section className="rounded-2xl border dark:border-dark-border bg-gov-gray-50/80 dark:bg-dark-bg/50 flex flex-col">
      <div className="p-3 border-b dark:border-dark-border">
        <h2 className="font-bold text-sm">{column.title}</h2>
        <p className="text-[10px] text-gov-gray-500">{column.hint}</p>
        <span className="text-xs font-mono text-gov-gray-400">{countLabel}</span>
      </div>
      <div className="flex-1 p-2 space-y-2 overflow-y-auto max-h-[60vh]">
        {cards.map((card) => (
          <KanbanCardView
            key={card.id}
            card={card}
            canWrite={canWrite}
            onPrev={idx > 0 ? () => onMove(card.id, order[idx - 1]) : undefined}
            onNext={idx < 2 ? () => onMove(card.id, order[idx + 1]) : undefined}
          />
        ))}
        {cards.length === 0 && (
          <p className="text-xs text-gov-gray-400 text-center py-8">
            {filtered && filterLabel
              ? `Sin instancias de ${filterLabel}`
              : 'Sin tarjetas'}
          </p>
        )}
      </div>
    </section>
  );
}

function KanbanCardView({
  card,
  canWrite,
  onPrev,
  onNext,
}: {
  card: KanbanCard;
  canWrite: boolean;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const slot = card.swarm_slot;
  return (
    <article className="bg-white dark:bg-dark-surface rounded-xl border dark:border-dark-border p-3 shadow-sm">
      <div className="flex gap-2">
        <GripVertical size={14} className="text-gov-gray-300 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 min-w-0">
            <h3 className="font-bold text-sm truncate">{card.title}</h3>
            {slot != null && slot > 1 && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-500 shrink-0">
                #{slot}
              </span>
            )}
          </div>
          {card.chat_scope && (
            <p className="text-[10px] font-mono text-gov-gray-400 mt-0.5 truncate" title={card.chat_scope}>
              chat: {card.chat_scope.length > 24 ? `${card.chat_scope.slice(0, 24)}…` : card.chat_scope}
            </p>
          )}
          {card.description && (
            <p className="text-xs text-gov-gray-500 mt-1 line-clamp-2">{card.description}</p>
          )}
          {card.worker_id && (
            <Link
              href={`/templates/${card.worker_id}`}
              className="text-[10px] font-mono text-gov-blue-700 mt-2 inline-block"
            >
              Abrir agente →
            </Link>
          )}
        </div>
      </div>
      {canWrite && (
        <div className="flex gap-1 mt-2">
          {onPrev && (
            <button
              type="button"
              onClick={onPrev}
              className="text-[10px] px-2 py-1 rounded-lg border dark:border-dark-border"
            >
              ←
            </button>
          )}
          {onNext && (
            <button
              type="button"
              onClick={onNext}
              className="text-[10px] px-2 py-1 rounded-lg border dark:border-dark-border ml-auto"
            >
              →
            </button>
          )}
        </div>
      )}
    </article>
  );
}
