'use client';

import { useCallback, useEffect, useState } from 'react';
import { MessageSquarePlus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { adminService, type AdminConversation } from '@/services/adminService';

const SECTION_OPTIONS = [
  { value: '', label: 'Todas las secciones' },
  { value: 'playground', label: 'Playground' },
  { value: 'kanban', label: 'Kanban' },
  { value: 'vnc', label: 'VNC' },
  { value: 'train', label: 'Train' },
  { value: 'root', label: 'Inicio' },
];

function formatRelative(iso: string): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso.slice(0, 16);
  const diff = Date.now() - t;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `hace ${days}d`;
  return new Date(t).toLocaleDateString();
}

export type ConversationInboxProps = {
  tenantId?: string;
  defaultSectionFilter?: string;
  activeSessionId: string | null;
  onSelect: (sessionId: string, meta?: AdminConversation) => void;
  variant?: 'sidebar' | 'compact';
  refreshToken?: number;
  /** Sincroniza título en panel/header cuando se renombra la conversación activa. */
  onTitleRenamed?: (sessionId: string, title: string) => void;
  className?: string;
};

export function ConversationInbox({
  tenantId = 'default',
  defaultSectionFilter = '',
  activeSessionId,
  onSelect,
  variant = 'sidebar',
  refreshToken = 0,
  onTitleRenamed,
  className = '',
}: ConversationInboxProps) {
  const [items, setItems] = useState<AdminConversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [section, setSection] = useState(defaultSectionFilter);
  const [worker, setWorker] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminService.listConversations({
        tenant_id: tenantId,
        section: section || undefined,
        worker: worker || undefined,
        q: q.trim() || undefined,
        limit: 80,
      });
      const list = res.conversations ?? [];
      setItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tenantId, section, worker, q]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  useEffect(() => {
    setSection(defaultSectionFilter);
  }, [defaultSectionFilter]);

  const createNew = async () => {
    try {
      const meta = await adminService.createConversation(
        {
          section: defaultSectionFilter || section || 'other',
          worker_id: worker || undefined,
        },
        tenantId
      );
      onSelect(meta.session_id, meta);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear');
    }
  };

  const renameTitle = async (sid: string, title: string) => {
    const meta = await adminService.patchConversation(sid, title, tenantId);
    setItems((prev) =>
      prev.map((c) => (c.session_id === sid ? { ...c, title: meta.title || title } : c))
    );
    if (activeSessionId === sid) onTitleRenamed?.(sid, meta.title || title);
  };

  const remove = async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('¿Eliminar esta conversación y su historial?')) return;
    try {
      await adminService.deleteConversation(sid, tenantId);
      if (activeSessionId === sid) {
        const next = items.find((c) => c.session_id !== sid);
        if (next) onSelect(next.session_id, next);
        else await createNew();
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo eliminar');
    }
  };

  const isCompact = variant === 'compact';

  return (
    <aside
      className={`flex flex-col min-h-0 border-r dark:border-dark-border bg-gov-gray-50/80 dark:bg-dark-bg/80 shrink-0 ${
        isCompact ? 'w-full h-full min-h-0' : 'w-[280px] min-w-[240px]'
      } ${className}`}
    >
      <div className="p-3 border-b dark:border-dark-border shrink-0">
        <InboxToolbar onNew={createNew} onRefresh={load} loading={loading} />
      </div>

      <InboxFilters
        q={q}
        setQ={setQ}
        section={section}
        setSection={setSection}
        worker={worker}
        setWorker={setWorker}
        showSectionFilter={!defaultSectionFilter}
      />

      {error && <p className="text-xs text-red-600 px-3 py-1">{error}</p>}

      <ul className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
        {loading && items.length === 0 && (
          <li className="text-xs text-gov-gray-400 text-center py-6">Cargando…</li>
        )}
        {!loading && items.length === 0 && (
          <li className="text-xs text-gov-gray-400 text-center py-6">Sin conversaciones</li>
        )}
        {items.map((c) => {
          const active = c.session_id === activeSessionId;
          return (
            <li key={c.session_id}>
              <button
                type="button"
                onClick={() => onSelect(c.session_id, c)}
                className={`w-full text-left rounded-xl px-3 py-2.5 text-sm transition-colors group ${
                  active
                    ? 'bg-gov-blue-700 text-white'
                    : 'hover:bg-white dark:hover:bg-dark-surface border border-transparent hover:border-gov-gray-200 dark:hover:border-dark-border'
                }`}
              >
                <InboxRowTitle
                  active={active}
                  compact={isCompact}
                  title={c.title || c.session_id}
                  onRename={(next) => renameTitle(c.session_id, next)}
                  onRemove={(e) => void remove(c.session_id, e)}
                />
                <p className={`text-[10px] mt-0.5 line-clamp-2 ${active ? 'text-white/80' : 'text-gov-gray-500'}`}>
                  {c.last_message_preview || '—'}
                </p>
                <InboxRowMeta
                  active={active}
                  updatedAt={c.updated_at}
                  section={c.section}
                  worker={c.last_worker_id}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

function InboxToolbar({
  onNew,
  onRefresh,
  loading,
}: {
  onNew: () => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  loading: boolean;
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2 mb-2">
        <h2 className="text-xs font-black uppercase tracking-wider text-gov-gray-600 dark:text-dark-muted">
          Conversaciones
        </h2>
        <button
          type="button"
          onClick={() => void onRefresh()}
          disabled={loading}
          className="p-1 rounded-lg text-gov-gray-500 hover:bg-gov-gray-200/80 dark:hover:bg-dark-border disabled:opacity-50"
          aria-label="Actualizar lista"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>
      <button
        type="button"
        onClick={() => void onNew()}
        className="w-full flex items-center justify-center gap-1.5 py-2 text-xs font-bold rounded-xl bg-gov-blue-700 text-white hover:bg-gov-blue-800"
      >
        <MessageSquarePlus size={14} aria-hidden />
        Nueva conversación
      </button>
    </>
  );
}

function InboxRowTitle({
  active,
  compact,
  title,
  onRename,
  onRemove,
}: {
  active: boolean;
  compact?: boolean;
  title: string;
  onRename: (title: string) => Promise<void>;
  onRemove: (e: React.MouseEvent) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-1">
      <EditableConversationTitle
        value={title}
        onSave={onRename}
        active={active}
        compact={compact}
      />
      <button
        type="button"
        onClick={onRemove}
        className={`shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 ${
          active ? 'text-white/80 hover:text-white' : 'text-gov-gray-400 hover:text-red-600'
        }`}
        aria-label="Eliminar conversación"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

function InboxRowMeta({
  active,
  updatedAt,
  section,
  worker,
}: {
  active: boolean;
  updatedAt: string;
  section: string;
  worker: string;
}) {
  return (
    <div
      className={`flex flex-wrap gap-1 mt-1.5 text-[9px] font-bold uppercase tracking-wide ${
        active ? 'text-white/70' : 'text-gov-gray-400'
      }`}
    >
      <span>{formatRelative(updatedAt)}</span>
      {section ? <span>· {section}</span> : null}
      {worker ? <span>· {worker}</span> : null}
    </div>
  );
}

function InboxFilters({
  q,
  setQ,
  section,
  setSection,
  worker,
  setWorker,
  showSectionFilter,
}: {
  q: string;
  setQ: (v: string) => void;
  section: string;
  setSection: (v: string) => void;
  worker: string;
  setWorker: (v: string) => void;
  showSectionFilter: boolean;
}) {
  return (
    <div className="px-3 pb-2 space-y-2 shrink-0">
      <label className="relative block">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gov-gray-400" />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar…"
          className="w-full pl-8 pr-2 py-1.5 text-xs border rounded-lg dark:border-dark-border dark:bg-dark-surface"
        />
      </label>
      {showSectionFilter && (
        <select
          value={section}
          onChange={(e) => setSection(e.target.value)}
          className="w-full text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-surface"
          aria-label="Filtrar por sección"
        >
          {SECTION_OPTIONS.map((o) => (
            <option key={o.value || 'all'} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
      <input
        type="text"
        value={worker}
        onChange={(e) => setWorker(e.target.value)}
        placeholder="Filtrar worker…"
        className="w-full text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-surface"
      />
    </div>
  );
}
