'use client';

import { useCallback, useState } from 'react';
import { MessageSquarePlus, Trash2 } from 'lucide-react';
import { ConversationQuickPicker } from '@/components/chat/ConversationQuickPicker';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { adminService, type AdminConversation } from '@/services/adminService';

export type ConversationManagePanelProps = {
  tenantId?: string;
  section?: string;
  activeSessionId: string;
  conversationTitle: string | null;
  refreshToken?: number;
  onSelect: (sessionId: string, meta?: AdminConversation) => void;
  onCreateNew: () => void | Promise<void>;
  onRename: (title: string) => Promise<void>;
  /** Tras eliminar o cambiar de conversación (p. ej. volver al tab Chat). */
  onAfterChange?: () => void;
  className?: string;
};

export function ConversationManagePanel({
  tenantId = 'default',
  section = '',
  activeSessionId,
  conversationTitle,
  refreshToken = 0,
  onSelect,
  onCreateNew,
  onRename,
  onAfterChange,
  className = '',
}: ConversationManagePanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayTitle =
    (conversationTitle || '').trim() ||
    (activeSessionId.length > 28
      ? `${activeSessionId.slice(0, 12)}…${activeSessionId.slice(-10)}`
      : activeSessionId);

  const handleSelect = useCallback(
    (id: string, meta?: AdminConversation) => {
      onSelect(id, meta);
      onAfterChange?.();
    },
    [onSelect, onAfterChange]
  );

  const handleCreate = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      await onCreateNew();
      onAfterChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear la conversación');
    } finally {
      setBusy(false);
    }
  }, [onCreateNew, onAfterChange]);

  const handleDelete = useCallback(async () => {
    if (!activeSessionId) return;
    if (!window.confirm('¿Eliminar esta conversación y su historial?')) return;
    setError(null);
    setBusy(true);
    try {
      await adminService.deleteConversation(activeSessionId, tenantId);
      const res = await adminService.listConversations({
        tenant_id: tenantId,
        ...(section ? { section } : {}),
        limit: 80,
      });
      const items = res.conversations ?? [];
      const next = items.find((c) => c.session_id !== activeSessionId);
      if (next) {
        onSelect(next.session_id, next);
      } else {
        await onCreateNew();
      }
      onAfterChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar');
    } finally {
      setBusy(false);
    }
  }, [activeSessionId, tenantId, section, onSelect, onCreateNew, onAfterChange]);

  return (
    <div
      className={`scrollbar-thin flex flex-col flex-1 min-h-0 overflow-y-auto p-4 space-y-4 ${className}`}
      role="tabpanel"
    >
      <ConversationQuickPicker
        tenantId={tenantId}
        section={section}
        activeSessionId={activeSessionId}
        refreshToken={refreshToken}
        onSelect={handleSelect}
        onCreateNew={() => void handleCreate()}
        conversationTitle={displayTitle}
        onRenameConversation={onRename}
      />

      <section className="rounded-2xl border dark:border-dark-border p-3 space-y-3 bg-white dark:bg-dark-surface">
        <p className="text-[10px] font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
          Nombre
        </p>
        <EditableConversationTitle
          value={displayTitle}
          onSave={onRename}
          className="text-sm w-full"
        />
        <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted font-mono break-all">
          ID: {activeSessionId}
        </p>
      </section>

      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleCreate()}
          className="flex-1 flex items-center justify-center gap-2 min-h-[44px] px-3 py-2 rounded-xl bg-gov-blue-700 text-white text-xs font-bold hover:bg-gov-blue-800 disabled:opacity-50"
        >
          <MessageSquarePlus size={16} aria-hidden />
          Nueva conversación
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleDelete()}
          className="flex-1 flex items-center justify-center gap-2 min-h-[44px] px-3 py-2 rounded-xl border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-400 text-xs font-bold hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50"
        >
          <Trash2 size={16} aria-hidden />
          Eliminar
        </button>
      </div>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
