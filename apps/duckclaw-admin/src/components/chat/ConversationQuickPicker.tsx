'use client';

import { useCallback, useEffect, useState } from 'react';
import { MessageSquarePlus } from 'lucide-react';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { adminService, type AdminConversation } from '@/services/adminService';

type Props = {
  tenantId?: string;
  section?: string;
  activeSessionId: string | null;
  onSelect: (sessionId: string, meta?: AdminConversation) => void;
  onCreateNew?: () => void | Promise<void>;
  /** Si false, oculta + (p. ej. burbuja: nueva conv en cabecera). Por defecto false cuando hay renombrar. */
  showCreateButton?: boolean;
  /** Título actual (para renombrar inline junto al desplegable). */
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  refreshToken?: number;
  className?: string;
};

/** Selector nativo (móvil-friendly) + editor de título inline (sin botón + cuando hay renombrar). */
export function ConversationQuickPicker({
  tenantId = 'default',
  section = '',
  activeSessionId,
  onSelect,
  onCreateNew,
  showCreateButton,
  conversationTitle,
  onRenameConversation,
  refreshToken = 0,
  className = '',
}: Props) {
  const [items, setItems] = useState<AdminConversation[]>([]);
  const [loading, setLoading] = useState(false);

  const showNewButton =
    (showCreateButton ?? !onRenameConversation) && Boolean(onCreateNew);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminService.listConversations({
        tenant_id: tenantId,
        ...(section ? { section } : {}),
        limit: 80,
      });
      setItems(res.conversations ?? []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tenantId, section]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const sessionIdLabel = (sessionId: string) =>
    sessionId.length > 24 ? `${sessionId.slice(0, 10)}…${sessionId.slice(-8)}` : sessionId;

  const labelFor = (c: Pick<AdminConversation, 'session_id' | 'title'>) => {
    const title = (c.title || '').trim();
    if (title) return title;
    return sessionIdLabel(c.session_id || '');
  };

  const activeTitle =
    (conversationTitle || '').trim() ||
    (activeSessionId
      ? labelFor(
          items.find((c) => c.session_id === activeSessionId) ?? {
            session_id: activeSessionId,
            title: '',
          }
        )
      : '');

  return (
    <div
      className={`flex flex-col gap-1 min-w-0 w-full relative z-30 touch-manipulation ${className}`}
    >
      <span className="text-[10px] font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
        Conversación
      </span>
      <div className="flex gap-2 items-stretch min-w-0">
        <select
          value={activeSessionId ?? ''}
          disabled={loading || !items.length}
          onChange={(e) => {
            const id = e.target.value;
            const meta = items.find((c) => c.session_id === id);
            if (id) onSelect(id, meta);
          }}
          className="flex-1 min-w-0 text-sm px-3 py-2.5 min-h-[44px] border rounded-xl dark:border-dark-border dark:bg-dark-bg truncate"
          aria-label="Seleccionar conversación"
        >
          {!activeSessionId && <option value="">—</option>}
          {items.map((c) => (
            <option key={c.session_id} value={c.session_id}>
              {labelFor(c)}
            </option>
          ))}
        </select>
        {onRenameConversation && activeSessionId ? (
          <EditableConversationTitle
            value={activeTitle}
            onSave={onRenameConversation}
            trigger="iconButton"
          />
        ) : null}
        {showNewButton ? (
          <button
            type="button"
            onClick={() => void onCreateNew?.()}
            className="shrink-0 px-3 py-2.5 min-h-[44px] min-w-[44px] rounded-xl bg-gov-blue-700 text-white hover:bg-gov-blue-800 flex items-center justify-center gap-1 text-xs font-bold"
            aria-label="Nueva conversación"
            title="Nueva conversación"
          >
            <MessageSquarePlus size={16} aria-hidden />
          </button>
        ) : null}
      </div>
    </div>
  );
}
