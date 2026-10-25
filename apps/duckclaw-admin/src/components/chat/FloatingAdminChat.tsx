'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Maximize2, Settings2, X } from 'lucide-react';
import {
  Pm2LiveLogsControls,
  Pm2LiveLogsProvider,
  Pm2LiveLogsViewport,
} from '@/components/admin/Pm2LiveLogsPanel';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { ChatSettingsPanel } from '@/components/chat/ChatSettingsPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { useFloatingChatUnread } from '@/components/chat/useFloatingChatUnread';
import { usePlaygroundChatToggles } from '@/components/playground/usePlaygroundChatToggles';
import { titleForAdminPath } from '@/config/adminNav';
import { adminService } from '@/services/adminService';
import { sectionFromPath } from '@/lib/conversationStorage';
import {
  defaultKnowledgeScope,
  normalizeKnowledgeScope,
  type KnowledgeScope,
} from '@/lib/knowledgeScope';
import {
  projectIdFromPathname,
  readLastProjectId,
} from '@/lib/floatingChatProject';
import { resolveWorkerDisplayName } from '@/lib/workerOptions';
import { CHAT_DRAWER_WIDTH_PX, useLayoutUiStore } from '@/store/layoutUiStore';

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
  const onPlayground =
    pathname === '/playground' || (pathname?.startsWith('/playground/') ?? false);
  const [tenantId, setTenantId] = useState<string | undefined>();
  const [logsSplitOpen, setLogsSplitOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolUsageEnabled, setToolUsageEnabled] = useState(true);
  const [projectOverride, setProjectOverride] = useState<string | null>(null);
  const {
    suggestionsEnabled,
    notificationsEnabled,
    handleSuggestionsToggle,
    handleNotificationsToggle,
  } = usePlaygroundChatToggles();
  const routeProjectId = useMemo(() => {
    const fromUrl = (searchParams.get('project') || '').trim();
    if (fromUrl) return fromUrl;
    const fromPath = projectIdFromPathname(pathname);
    if (fromPath) return fromPath;
    return readLastProjectId();
  }, [pathname, searchParams]);
  const projectId = projectOverride ?? routeProjectId;
  const [knowledgeScope, setKnowledgeScope] = useState<KnowledgeScope>(() =>
    defaultKnowledgeScope(projectId)
  );

  const section = useMemo(() => sectionFromPath(pathname), [pathname]);
  const sectionTitle = titleForAdminPath(pathname);
  const pathWorker = useMemo(() => workerFromPath(pathname), [pathname]);
  const conv = useActiveConversation(tenantId, section, {
    defaultWorkerId: pathWorker,
    enabled: !onPlayground,
  });
  const { createConversation, selectConversation } = conv;
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: pathWorker,
    projectId,
    knowledgeScope,
    suggestionsEnabled,
    notificationsEnabled,
    // Solo activo con drawer abierto y fuera del playground (evita poll global).
    enabled: !onPlayground && Boolean(conv.sessionId) && open,
    onConversationActivity: conv.bumpRefresh,
    onConversationNotFound: conv.recoverMissingConversation,
  });
  const { workerId, loading, messages, historyLoading, scrollToBottom, config, reloadConfig } = chat;

  useEffect(() => {
    setKnowledgeScope((prev) => normalizeKnowledgeScope(config?.knowledge_scope || prev, projectId));
  }, [config?.knowledge_scope, projectId]);

  const persistKnowledgeScope = useCallback(
    async (nextScope: KnowledgeScope) => {
      const normalized = normalizeKnowledgeScope(nextScope, projectId);
      setKnowledgeScope(normalized);
      if (!conv.sessionId) return;
      try {
        await adminService.setPlaygroundKnowledgeScope({
          chat_id: conv.sessionId,
          tenant_id: config?.effective_tenant_id,
          knowledge_scope: normalized,
          project_id: projectId || undefined,
        });
        reloadConfig();
      } catch {
        /* keep local selection */
      }
    },
    [conv.sessionId, config?.effective_tenant_id, projectId, reloadConfig]
  );
  const activeWorkerLabel = resolveWorkerDisplayName(config?.workers, workerId) || 'Agente';

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
    if (onPlayground) return;
    adminService
      .getPlaygroundConfig()
      .then((c) => setTenantId(c.effective_tenant_id))
      .catch(() => undefined);
  }, [onPlayground]);

  const htmlDashboardDeliverable =
    (pathname?.includes('/productividad') ?? false) &&
    searchParams.get('view') === 'entregables' &&
    searchParams.get('deliverable') === 'html';

  if (onPlayground) {
    return null;
  }

  const headerActions = (
    <div className="flex items-center justify-end gap-1 shrink-0">
      <button
        type="button"
        onClick={() => setSettingsOpen((v) => !v)}
        disabled={!conv.sessionId}
        aria-expanded={settingsOpen}
        className={`p-1.5 rounded-lg hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50 ${
          settingsOpen ? 'bg-gov-gray-100 text-gov-blue-800 dark:bg-dark-bg' : 'text-gov-blue-700'
        }`}
        title={settingsOpen ? 'Ocultar settings' : 'Settings'}
        aria-label={settingsOpen ? 'Ocultar settings' : 'Mostrar settings'}
      >
        <Settings2 size={16} aria-hidden />
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
        emptyHint={
          htmlDashboardDeliverable
            ? 'Pide un dashboard HTML o publica con publish_custom_report (report_id = id de esta conversación).'
            : `Pregunta sobre ${sectionTitle}…`
        }
        showWorkerLink={false}
        showToolUsage={toolUsageEnabled}
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

  const settingsSheet =
    settingsOpen && conv.sessionId ? (
      <div
        className="absolute inset-0 z-20 flex flex-col border-t border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface"
        role="region"
        aria-label="Settings del chat"
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-gov-gray-200 px-4 py-2 dark:border-dark-border">
          <span className="text-sm font-medium text-gov-gray-900 dark:text-dark-text">Settings</span>
          <button
            type="button"
            onClick={() => setSettingsOpen(false)}
            className="p-1.5 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar settings"
          >
            <X size={16} aria-hidden />
          </button>
        </div>
        <div className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-3">
          <ChatSettingsPanel
            chatId={conv.sessionId}
            chat={chat}
            projectId={projectId}
            onProjectIdChange={setProjectOverride}
            knowledgeScope={knowledgeScope}
            onKnowledgeScopeChange={(scope) => void persistKnowledgeScope(scope)}
            toolUsageEnabled={toolUsageEnabled}
            onToolUsageToggle={() => setToolUsageEnabled((v) => !v)}
            suggestionsEnabled={suggestionsEnabled}
            onSuggestionsToggle={handleSuggestionsToggle}
            notificationsEnabled={notificationsEnabled}
            onNotificationsToggle={handleNotificationsToggle}
          />
        </div>
      </div>
    ) : null;

  return (
    <div
      className={`shrink-0 overflow-hidden transition-[width] duration-300 ease-out border-l dark:border-dark-border bg-white dark:bg-dark-surface ${
        open ? '' : 'border-l-0'
      }`}
      style={{ width: open ? CHAT_DRAWER_WIDTH_PX : 0 }}
    >
      <Pm2LiveLogsProvider autoStart={logsSplitOpen}>
        <div
          className="flex h-full min-h-0 flex-col"
          style={{ width: CHAT_DRAWER_WIDTH_PX, minWidth: CHAT_DRAWER_WIDTH_PX }}
        >
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
              {chatPanel}
              {settingsSheet}
            </div>
            {logsSplitOpen ? (
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-t border-gov-gray-200 bg-white text-gov-gray-800 dark:border-dark-border dark:bg-slate-950 dark:text-slate-200">
                <Pm2LiveLogsControls variant="studio" />
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                  <Pm2LiveLogsViewport className="h-full min-h-0" />
                </div>
              </div>
            ) : null}
          </div>
          <div className="shrink-0 border-t border-gov-gray-200 dark:border-dark-border">
            <button
              type="button"
              onClick={() => setLogsSplitOpen((v) => !v)}
              aria-pressed={logsSplitOpen}
              aria-label="Mostrar u ocultar logs PM2"
              title={logsSplitOpen ? 'Ocultar consola de logs' : 'Mostrar consola de logs'}
              data-testid="floating-chat-logs-toggle"
              className={`flex h-9 w-full items-center justify-center font-mono text-xs font-bold transition-colors ${
                logsSplitOpen
                  ? 'bg-gov-blue-700 text-white hover:bg-gov-blue-800 dark:bg-gov-blue-600'
                  : 'bg-gov-gray-50 text-gov-gray-600 hover:bg-gov-gray-100 dark:bg-dark-bg dark:text-dark-muted dark:hover:bg-dark-surface'
              }`}
            >
              {'</>'}
            </button>
          </div>
        </div>
      </Pm2LiveLogsProvider>
    </div>
  );
}

export { useFloatingChatUnread };
