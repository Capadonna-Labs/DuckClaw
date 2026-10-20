'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Bot, Pencil, Trash2 } from 'lucide-react';
import { adminService, type AdminConversation } from '@/services/adminService';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { unreadReplies } from '@/lib/conversationSeen';

import {
  formatConversationTime,
  historyWorkerLabel,
  uniqueConversationsBySession,
} from './playgroundHistoryHelpers';
import type { PlaygroundConfig } from './playgroundTypes';

const ACTIVITY: Record<string, { label: string; dot: string }> = {
  working: { label: 'Trabajando', dot: 'bg-emerald-500 animate-pulse' },
  awaiting_approval: { label: 'Espera tu aprobación', dot: 'bg-amber-500' },
  idle: { label: 'En reposo', dot: 'bg-gov-gray-300 dark:bg-dark-border' },
};
// ponytail: 15 s polling of the list; a push/SSE channel if it ever needs to be instant.
const REFRESH_MS = 15_000;

export function PlaygroundHistoryView({
  tenantId,
  workers,
  configLoading = false,
  configError = null,
  authHydrated = true,
  onRetryConfig,
  onSelectConversation,
}: {
  tenantId?: string;
  workers?: NonNullable<PlaygroundConfig>['workers'];
  configLoading?: boolean;
  configError?: string | null;
  authHydrated?: boolean;
  onRetryConfig?: () => void;
  onSelectConversation?: (id: string) => void;
}) {
  const [conversations, setConversations] = useState<AdminConversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);
  const uniqueConversations = useMemo(
    () => uniqueConversationsBySession(conversations),
    [conversations]
  );

  useEffect(() => {
    if (!tenantId?.trim()) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // admin-conv-* indexa section="" (filtrar section=playground ocultaba hilos reales del tenant).
    adminService.listConversations({ tenant_id: tenantId, limit: 80 })
      .then((res) => {
        if (!cancelled) setConversations(res.conversations ?? []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudo cargar el historial');
          setConversations([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // Silent refresh so the traffic light and the unread badges follow the agents.
    const timer = window.setInterval(() => {
      adminService.listConversations({ tenant_id: tenantId, limit: 80 })
        .then((res) => {
          if (!cancelled) setConversations(res.conversations ?? []);
        })
        .catch(() => undefined);
    }, REFRESH_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [tenantId]);

  const renameHistoryConversation = async (sessionId: string, title: string) => {
    setError(null);
    const meta = await adminService.patchConversation(sessionId, title, tenantId);
    setConversations((prev) =>
      prev.map((item) =>
        item.session_id === sessionId ? { ...item, title: meta.title || title } : item
      )
    );
  };

  const deleteHistoryConversation = async (conversation: AdminConversation) => {
    const title = conversation.title || conversation.session_id;
    const confirmed = window.confirm(
      `Eliminar esta conversación?\n\n"${title}"\n\nSe borrará del historial y no aparecerá en la bandeja.`
    );
    if (!confirmed) return;
    setError(null);
    setDeletingSessionId(conversation.session_id);
    try {
      await adminService.deleteConversation(conversation.session_id, tenantId);
      setConversations((prev) => prev.filter((item) => item.session_id !== conversation.session_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo eliminar la conversación');
    } finally {
      setDeletingSessionId(null);
    }
  };

  return (
    <section className="flex-1 min-w-0 min-h-[calc(100vh-8rem)] lg:min-h-0 lg:h-full bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 p-4 border-b dark:border-dark-border">
        <div>
          <h1 className="text-xl font-black dark:text-dark-text flex items-center gap-2">
            <Bot size={22} /> Historial
          </h1>
          <p className="text-xs text-gov-gray-500 mt-0.5">
            Conversaciones recientes del Playground
          </p>
        </div>
        <Link
          href="/playground?new=1"
          className="text-xs font-bold rounded-xl bg-gov-blue-700 text-white px-3 py-2 hover:bg-gov-blue-800"
        >
          Nueva conversación
        </Link>
      </header>
      <div className="scrollbar-thin h-full min-h-0 overflow-y-auto p-4">
        {!tenantId?.trim() && !authHydrated && (
          <p className="text-sm text-gov-gray-400 text-center py-10">Cargando perfil…</p>
        )}
        {authHydrated && !tenantId?.trim() && (
          <div className="rounded-3xl border border-dashed dark:border-dark-border p-10 text-center">
            <p className="font-bold dark:text-dark-text">Perfil sin tenant</p>
            <p className="text-sm text-gov-gray-500 mt-1">
              No se pudo resolver tu tenant. Recarga la página o vuelve a iniciar sesión.
            </p>
          </div>
        )}
        {tenantId?.trim() && configError && (
          <div className="rounded-3xl border border-amber-200 bg-amber-50 p-6 text-center dark:border-amber-900/50 dark:bg-amber-950/20">
            <p className="text-sm text-amber-900 dark:text-amber-200">{configError}</p>
            {onRetryConfig ? (
              <button
                type="button"
                onClick={onRetryConfig}
                className="mt-3 text-xs font-bold rounded-xl bg-gov-blue-700 text-white px-3 py-2 hover:bg-gov-blue-800"
              >
                Reintentar configuración
              </button>
            ) : null}
          </div>
        )}
        {tenantId?.trim() && (loading || (configLoading && !configError)) && (
          <p className="text-sm text-gov-gray-400 text-center py-10">Cargando historial…</p>
        )}
        {tenantId?.trim() && error && error !== configError && (
          <p className="text-sm text-red-600 text-center py-10">{error}</p>
        )}
        {tenantId?.trim() && !loading && !error && !(configLoading && !configError) && uniqueConversations.length === 0 && (
          <div className="rounded-3xl border border-dashed dark:border-dark-border p-10 text-center">
            <p className="font-bold dark:text-dark-text">Sin conversaciones</p>
            <p className="text-sm text-gov-gray-500 mt-1">Crea una conversación para verla aquí.</p>
          </div>
        )}
        {tenantId?.trim() && !loading && !error && !(configLoading && !configError) && uniqueConversations.length > 0 && (
          <ul className="grid gap-2">
            {uniqueConversations.map((conversation) => {
              const isRenaming = renamingSessionId === conversation.session_id;
              const unread = unreadReplies(conversation.session_id, conversation.message_count);
              const activity = ACTIVITY[conversation.activity || 'idle'] ?? ACTIVITY.idle;
              return (
              <li key={conversation.session_id}>
                <div className="flex items-stretch gap-2 rounded-2xl border dark:border-dark-border p-3 hover:border-gov-blue-300 hover:bg-gov-blue-50/50 dark:hover:bg-dark-bg transition-colors">
                  <button
                    type="button"
                    onClick={() => {
                      if (!isRenaming) onSelectConversation?.(conversation.session_id);
                    }}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="min-w-0">
                      <EditableConversationTitle
                        value={conversation.title || conversation.session_id}
                        onSave={async (title) => {
                          await renameHistoryConversation(conversation.session_id, title);
                          setRenamingSessionId(null);
                        }}
                        variant="history"
                        hideEditIcon
                        editing={isRenaming}
                        onEditingChange={(next) =>
                          setRenamingSessionId(next ? conversation.session_id : null)
                        }
                      />
                      <p className="text-xs text-gov-gray-500 mt-1 line-clamp-2">
                        {conversation.last_message_preview || 'Sin mensajes todavía'}
                      </p>
                    </div>
                    <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-400 mt-2 flex flex-wrap items-center gap-x-1.5">
                      <span
                        className="inline-flex items-center gap-1 normal-case tracking-normal text-gov-gray-600 dark:text-dark-muted"
                        title={conversation.activity_task || activity.label}
                      >
                        <span className={`inline-block h-2 w-2 rounded-full ${activity.dot}`} aria-hidden />
                        {activity.label}
                      </span>
                      <span aria-hidden>·</span>
                      {historyWorkerLabel(conversation, workers)} · {conversation.message_count} mensajes
                    </p>
                  </button>
                  <div className="flex shrink-0 flex-col items-center justify-between gap-1.5 py-0.5">
                    <span className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wide text-gov-gray-400 whitespace-nowrap">
                      {formatConversationTime(conversation.updated_at)}
                      {unread > 0 ? (
                        <span
                          className="min-w-[1.25rem] rounded-full bg-gov-blue-700 px-1.5 py-0.5 text-center text-[10px] font-bold normal-case text-white"
                          aria-label={`${unread} respuestas sin leer`}
                        >
                          {unread > 99 ? '99+' : unread}
                        </span>
                      ) : null}
                    </span>
                    <button
                      type="button"
                      onClick={() => setRenamingSessionId(conversation.session_id)}
                      className="rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-xs font-bold text-gov-gray-600 hover:border-gov-blue-300 hover:text-gov-blue-700 dark:border-dark-border dark:bg-dark-surface dark:text-dark-muted dark:hover:text-dark-cyan"
                      aria-label={`Renombrar conversación ${conversation.title || conversation.session_id}`}
                      title="Renombrar conversación"
                    >
                      <Pencil size={15} aria-hidden />
                      <span className="sr-only">Renombrar</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteHistoryConversation(conversation)}
                      disabled={deletingSessionId === conversation.session_id}
                      className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-50 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                      aria-label={`Eliminar conversación ${conversation.title || conversation.session_id}`}
                    >
                      <Trash2 size={15} aria-hidden />
                      <span className="sr-only">Eliminar</span>
                    </button>
                  </div>
                </div>
              </li>
            );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
