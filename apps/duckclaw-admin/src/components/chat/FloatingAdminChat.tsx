'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Bot, MessageSquare, X, Maximize2 } from 'lucide-react';
import { ThinkingDots } from '@/components/chat/ChatBubble';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { ConversationInbox } from '@/components/chat/ConversationInbox';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { useFloatingChatUnread } from '@/components/chat/useFloatingChatUnread';
import { titleForAdminPath } from '@/config/adminNav';
import { adminService } from '@/services/adminService';
import { sectionFromPath } from '@/lib/conversationStorage';

const BUBBLE_OFFSET_STORAGE_KEY = 'duckclaw-floating-chat-offset-x';
const BUBBLE_SIZE_PX = 48;
const EDGE_INSET_PX = 16;
const PANEL_WIDTH_PX = 560;
const PANEL_HEIGHT_PX = 720;

/** Si la ruta es /templates/[workerId], usar ese agente por defecto. */
function workerFromPath(pathname: string): string {
  const match = pathname.match(/^\/templates\/([^/]+)/);
  if (!match?.[1]) return '';
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function readStoredOffset(): number {
  if (typeof window === 'undefined') return 0;
  try {
    const raw = localStorage.getItem(BUBBLE_OFFSET_STORAGE_KEY);
    const n = raw ? Number(raw) : 0;
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

function maxDragOffset(): number {
  if (typeof window === 'undefined') return 0;
  return Math.max(0, window.innerWidth - BUBBLE_SIZE_PX - EDGE_INSET_PX * 2);
}

export function FloatingAdminChat() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [tenantId, setTenantId] = useState<string | undefined>();
  const [offsetX, setOffsetX] = useState(0);
  const dragRef = useRef({
    active: false,
    startX: 0,
    startOffset: 0,
    moved: false,
  });

  const section = useMemo(() => sectionFromPath(pathname), [pathname]);
  const sectionTitle = titleForAdminPath(pathname);
  const pathWorker = useMemo(() => workerFromPath(pathname), [pathname]);
  const conv = useActiveConversation(tenantId, section);
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: pathWorker,
    enabled: Boolean(conv.sessionId),
    onConversationActivity: conv.bumpRefresh,
  });
  const { workerId, loading, messages, historyLoading, scrollToBottom } = chat;
  const activeWorkerLabel = workerId || '…';

  // #region agent log
  useEffect(() => {
    fetch('http://127.0.0.1:7542/ingest/7eef0e1d-8424-45c4-8303-d7cb22712741', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Debug-Session-Id': 'fd1dbb',
      },
      body: JSON.stringify({
        sessionId: 'fd1dbb',
        hypothesisId: 'H2',
        location: 'FloatingAdminChat.tsx:open',
        message: 'panel open state',
        data: {
          open,
          sessionId: (conv.sessionId ?? '').slice(0, 24),
          messageCount: messages.length,
        },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
  }, [open, conv.sessionId, messages.length]);
  // #endregion

  const openPanel = useCallback(() => setOpen(true), []);

  const {
    unreadCount,
    badgeText,
    badgeLabel,
    ensureNotificationPermission,
    notificationPermission: notifyPerm,
  } = useFloatingChatUnread({
    sessionId: conv.sessionId,
    messages,
    panelOpen: open,
    loading,
    historyLoading: historyLoading || conv.bootstrapping,
    sectionTitle,
    workerLabel: activeWorkerLabel,
    onOpenPanel: openPanel,
  });

  useEffect(() => {
    if (!open || !conv.sessionId || historyLoading) return;
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(() => scrollToBottom('auto'));
    });
    return () => cancelAnimationFrame(id);
  }, [open, conv.sessionId, historyLoading, messages.length, scrollToBottom]);

  useEffect(() => {
    adminService
      .getPlaygroundConfig()
      .then((c) => setTenantId(c.effective_tenant_id))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setOffsetX(readStoredOffset());
  }, []);

  useEffect(() => {
    const onResize = () => {
      setOffsetX((prev) => Math.min(prev, maxDragOffset()));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const persistOffset = useCallback((value: number) => {
    const clamped = Math.min(Math.max(0, value), maxDragOffset());
    setOffsetX(clamped);
    try {
      localStorage.setItem(BUBBLE_OFFSET_STORAGE_KEY, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  const onBubblePointerDown = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      if (e.button !== 0) return;
      dragRef.current = {
        active: true,
        startX: e.clientX,
        startOffset: offsetX,
        moved: false,
      };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [offsetX]
  );

  const onBubblePointerMove = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      if (!dragRef.current.active) return;
      const delta = dragRef.current.startX - e.clientX;
      if (Math.abs(delta) > 4) dragRef.current.moved = true;
      persistOffset(dragRef.current.startOffset + delta);
    },
    [persistOffset]
  );

  const endBubbleDrag = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }, []);

  const onBubbleClick = useCallback(() => {
    if (dragRef.current.moved) {
      dragRef.current.moved = false;
      return;
    }
    setOpen((wasOpen) => {
      if (!wasOpen) void ensureNotificationPermission();
      return !wasOpen;
    });
  }, [ensureNotificationPermission]);

  const maxOffset = maxDragOffset();
  const panelOpensRight = maxOffset > 0 && offsetX > maxOffset * 0.35;

  if (pathname === '/playground' || pathname.startsWith('/playground/')) {
    return null;
  }

  return (
    <div
      className={`fixed bottom-4 z-40 flex flex-col gap-2 pointer-events-none ${
        panelOpensRight ? 'items-start' : 'items-end'
      }`}
      style={{ right: `calc(${EDGE_INSET_PX}px + ${offsetX}px)` }}
    >
      {notifyPerm === 'denied' && !open && (
        <p
          className="pointer-events-none max-w-[220px] rounded-lg bg-amber-50 px-2 py-1 text-[10px] text-amber-900 shadow dark:bg-amber-950/90 dark:text-amber-100"
          role="status"
        >
          Notificaciones bloqueadas en el navegador. Actívalas en Ajustes del sitio.
        </p>
      )}
      {open && (
        <div
          className={`pointer-events-auto relative flex flex-col animate-in slide-in-from-bottom-4 fade-in duration-200 ${
            panelOpensRight ? 'self-start' : 'self-end'
          }`}
          style={{
            width: PANEL_WIDTH_PX,
            height: `min(${PANEL_HEIGHT_PX}px, calc(100vh - 2rem))`,
            maxWidth: 'calc(100vw - 2rem)',
          }}
          role="dialog"
          aria-label={`Chat en ${sectionTitle}`}
        >
          <div className="flex flex-1 min-h-0 pointer-events-auto overflow-hidden">
            {inboxOpen && conv.sessionId && (
              <ConversationInbox
                tenantId={tenantId}
                defaultSectionFilter=""
                activeSessionId={conv.sessionId}
                refreshToken={conv.refreshToken}
                variant="compact"
                onSelect={(id, meta) => {
                  conv.selectConversation(id, meta?.title);
                  setInboxOpen(false);
                }}
                onTitleRenamed={(_id, title) => conv.syncConversationTitle(title)}
                className="border-r dark:border-dark-border"
              />
            )}
            {conv.bootstrapping || !conv.sessionId ? (
              <p className="flex-1 flex items-center justify-center text-xs text-gov-gray-400 p-4">
                Cargando…
              </p>
            ) : (
              <AdminChatPanel
                key={conv.sessionId}
                chatId={conv.sessionId}
                chat={chat}
                variant="compact"
                sectionTitle={sectionTitle}
                conversationTitle={conv.conversationTitle}
                emptyHint={`Pregunta sobre ${sectionTitle}…`}
                showWorkerLink={false}
                headerActions={
                  <div className="flex items-center justify-end gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => setInboxOpen((v) => !v)}
                      className="p-1.5 rounded-lg text-gov-blue-700 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                      title="Conversaciones"
                      aria-label="Mostrar conversaciones"
                      aria-expanded={inboxOpen}
                    >
                      <MessageSquare size={16} />
                    </button>
                    <Link
                      href="/playground"
                      className="p-1.5 rounded-lg text-gov-blue-700 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                      title="Abrir Playground completo"
                      aria-label="Abrir Playground completo"
                    >
                      <Maximize2 size={16} />
                    </Link>
                    <button
                      type="button"
                      onClick={() => setOpen(false)}
                      className="p-1.5 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                      aria-label={loading ? 'Minimizar chat (el agente sigue pensando)' : 'Cerrar chat'}
                      title={loading ? 'Minimizar y seguir en segundo plano' : 'Cerrar'}
                    >
                      <X size={18} />
                    </button>
                  </div>
                }
                className="flex-1 min-h-0"
              />
            )}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={onBubbleClick}
        onPointerDown={onBubblePointerDown}
        onPointerMove={onBubblePointerMove}
        onPointerUp={endBubbleDrag}
        onPointerCancel={endBubbleDrag}
        className={`pointer-events-auto relative flex items-center justify-center size-12 rounded-full bg-gov-blue-700 text-white shadow-lg hover:bg-gov-blue-800 transition-colors touch-none cursor-grab active:cursor-grabbing ${
          !open && loading ? 'ring-2 ring-gov-blue-400/80 ring-offset-2 ring-offset-transparent' : ''
        }`}
        aria-expanded={open}
        aria-busy={loading}
        aria-label={
          open
            ? loading
              ? 'Minimizar asistente; el agente sigue pensando'
              : badgeLabel
                ? `Cerrar asistente, ${badgeLabel}`
                : 'Cerrar asistente'
            : loading
              ? `Agente pensando (${activeWorkerLabel}). Abrir chat. Arrastra para mover.`
              : badgeLabel
                ? `Abrir asistente, ${badgeLabel}, agente activo ${activeWorkerLabel}. Arrastra para mover.`
                : `Abrir asistente, agente activo ${activeWorkerLabel}. Arrastra para mover.`
        }
      >
        {open ? (
          <X size={22} aria-hidden />
        ) : loading ? (
          <ThinkingDots size="sm" className="text-white" />
        ) : (
          <Bot size={22} aria-hidden />
        )}
        {!open && unreadCount > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 z-10 flex min-w-[1.125rem] h-[1.125rem] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-none text-white shadow ring-2 ring-white dark:ring-dark-bg"
            aria-label={badgeLabel}
          >
            {badgeText}
          </span>
        )}
      </button>
    </div>
  );
}
