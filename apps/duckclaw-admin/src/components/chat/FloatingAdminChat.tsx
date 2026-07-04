'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Maximize2, X } from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { useFloatingChatUnread } from '@/components/chat/useFloatingChatUnread';
import { titleForAdminPath } from '@/config/adminNav';
import { adminService } from '@/services/adminService';
import { sectionFromPath } from '@/lib/conversationStorage';
import {
  projectIdFromPathname,
  readLastProjectId,
} from '@/lib/floatingChatProject';
import { useLayoutUiStore } from '@/store/layoutUiStore';

function workerFromPath(pathname: string): string {
  const match = pathname.match(/^\/templates\/([^/]+)/);
  if (!match?.[1]) return '';
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export function FloatingAdminChat() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { chatDrawerOpen: open, setChatDrawerOpen: setOpen } = useLayoutUiStore();
  const [tenantId, setTenantId] = useState<string | undefined>();
  const projectId = useMemo(() => {
    const fromUrl = (searchParams.get('project') || '').trim();
    if (fromUrl) return fromUrl;
    const fromPath = projectIdFromPathname(pathname);
    if (fromPath) return fromPath;
    return readLastProjectId();
  }, [pathname, searchParams]);

  const section = useMemo(() => sectionFromPath(pathname), [pathname]);
  const sectionTitle = titleForAdminPath(pathname);
  const pathWorker = useMemo(() => workerFromPath(pathname), [pathname]);
  const conv = useActiveConversation(tenantId, section);
  const { createConversation, selectConversation } = conv;
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: pathWorker,
    projectId,
    enabled: Boolean(conv.sessionId),
    onConversationActivity: conv.bumpRefresh,
  });
  const { workerId, loading, messages, historyLoading, scrollToBottom } = chat;
  const activeWorkerLabel = workerId || '…';

  const openPanel = useCallback(() => setOpen(true), [setOpen]);

  const {
    unreadCount,
    ensureNotificationPermission,
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

  if (pathname === '/playground' || pathname.startsWith('/playground/')) {
    return null;
  }

  const headerActions = (
    <div className="flex items-center justify-end gap-1 shrink-0">
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
  );

  const chatPanel =
    conv.bootstrapping || !conv.sessionId ? (
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
        headerActions={headerActions}
        onRenameConversation={conv.renameConversation}
        conversationManage={{
          tenantId,
          section: '',
          refreshToken: conv.refreshToken,
          onSelect: (id, meta) => selectConversation(id, meta?.title),
          onCreateNew: () => void createConversation(),
        }}
        className="flex-1 min-h-0 w-full"
      />
    );

  return (
    <div
      className={`shrink-0 overflow-hidden transition-[width] duration-300 ease-out border-l dark:border-dark-border bg-white dark:bg-dark-surface ${
        open ? 'w-[420px]' : 'w-0 border-l-0'
      }`}
    >
      <div className="flex flex-col h-full w-[420px] min-w-[420px]">
        {chatPanel}
      </div>
    </div>
  );
}

export { useFloatingChatUnread };
