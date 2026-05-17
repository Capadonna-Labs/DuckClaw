'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import type { KanbanCard, KanbanStatus } from '@/lib/kanbanTypes';
import { KANBAN_COLUMNS } from '@/lib/kanbanTypes';
import { useAuthStore } from '@/store/authStore';
import { PageShell } from '@/components/admin/PageShell';
import { Plus, RefreshCw, GripVertical } from 'lucide-react';

export default function KanbanPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [cards, setCards] = useState<KanbanCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
            Organiza la creación de agentes como en un tablero Trello. Inspirado en el flujo{' '}
            <strong>Plan → Prompt → Review</strong> de{' '}
            <a
              href="https://vibekanban.com/"
              target="_blank"
              rel="noreferrer"
              className="text-gov-blue-700 underline"
            >
              Vibe Kanban
            </a>
            .
          </p>
        </div>
        <div className="flex gap-2">
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
        {KANBAN_COLUMNS.map((col) => (
          <KanbanColumn
            key={col.id}
            column={col}
            cards={cards.filter((c) => c.status === col.id)}
            canWrite={canWrite}
            onMove={moveCard}
          />
        ))}
      </div>
    </PageShell>
  );
}

function KanbanColumn({
  column,
  cards,
  canWrite,
  onMove,
}: {
  column: (typeof KANBAN_COLUMNS)[number];
  cards: KanbanCard[];
  canWrite: boolean;
  onMove: (id: string, status: KanbanStatus) => void;
}) {
  const order: KanbanStatus[] = ['pendiente', 'en_progreso', 'completo'];
  const idx = order.indexOf(column.id);

  return (
    <section className="rounded-2xl border dark:border-dark-border bg-gov-gray-50/80 dark:bg-dark-bg/50 flex flex-col">
      <div className="p-3 border-b dark:border-dark-border">
        <h2 className="font-bold text-sm">{column.title}</h2>
        <p className="text-[10px] text-gov-gray-500">{column.hint}</p>
        <span className="text-xs font-mono text-gov-gray-400">{cards.length}</span>
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
          <p className="text-xs text-gov-gray-400 text-center py-8">Sin tarjetas</p>
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
  return (
    <article className="bg-white dark:bg-dark-surface rounded-xl border dark:border-dark-border p-3 shadow-sm">
      <div className="flex gap-2">
        <GripVertical size={14} className="text-gov-gray-300 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className="font-bold text-sm truncate">{card.title}</h3>
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
