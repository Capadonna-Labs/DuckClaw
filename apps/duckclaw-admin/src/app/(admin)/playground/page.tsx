'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import {
  ArrowLeft,
  FolderOpen,
  Settings2,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
  Terminal,
  X,
} from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { ChatLlmSelectors } from '@/components/chat/ChatLlmSelectors';
import { ChatSlmSelector } from '@/components/chat/ChatSlmSelector';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';
import { ScrollFabPair } from '@/components/shared/ScrollFabPair';
import { useScrollFabPair } from '@/components/shared/useScrollFabPair';
import { workerOptionId, workerOptionIds, workerOptionLabel } from '@/lib/workerOptions';
import { PlaygroundRagProjectWarning } from '@/components/playground/PlaygroundRagProjectWarning';
import { PlaygroundRunSettingsPanel } from '@/components/playground/PlaygroundRunSettingsPanel';
import {
  Pm2LiveLogsControls,
  Pm2LiveLogsProvider,
  Pm2LiveLogsViewport,
} from '@/components/admin/Pm2LiveLogsPanel';
import { writeLastProjectId } from '@/lib/floatingChatProject';
import { useAuthStore } from '@/store/authStore';
import {
  defaultKnowledgeScope,
  knowledgeScopeLabel,
  normalizeKnowledgeScope,
  type KnowledgeScope,
} from '@/lib/knowledgeScope';
import { readStoredWorker } from '@/components/chat/adminChatPure';
import {
  readPlaygroundLastLlm,
  readPlaygroundLastWorker,
  writePlaygroundLastLlm,
  writePlaygroundLastWorker,
} from '@/lib/playgroundLastSelection';

import { PlaygroundHistoryView } from '@/components/playground/PlaygroundHistoryView';
import {
  ChatCommandsPanel,
  ProjectAgentControls,
  SettingValue,
  SettingsModal,
} from '@/components/playground/PlaygroundSettingsParts';
import type {
  PlaygroundConfig,
  PlaygroundSettingsModal,
} from '@/components/playground/playgroundTypes';

export default function PlaygroundPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialWorker = searchParams.get('worker') || '';
  const initialProject = searchParams.get('project') || '';
  const [panelOpen, setPanelOpen] = useState(true);
  const [mainScrollEl, setMainScrollEl] = useState<HTMLElement | null>(null);
  const [systemPreview, setSystemPreview] = useState('');
  const [settingsModal, setSettingsModal] = useState<PlaygroundSettingsModal>(null);
  const [config, setConfig] = useState<PlaygroundConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const usuario = useAuthStore((s) => s.usuario);
  const authHydrated = useAuthStore((s) => s.hasHydrated);
  const profileTenantId = usuario?.profile?.tenant_id?.trim() || '';
  const effectiveTenantId = config?.effective_tenant_id?.trim() || profileTenantId || undefined;
  const [workerId, setWorkerId] = useState(initialWorker);
  const [projectId, setProjectId] = useState(initialProject);
  const [knowledgeScope, setKnowledgeScope] = useState<KnowledgeScope>(
    defaultKnowledgeScope(initialProject)
  );
  const [indexedKnowledgeSources, setIndexedKnowledgeSources] = useState(0);
  const [logsPanelOpen, setLogsPanelOpen] = useState(false);
  const [sandboxToggling, setSandboxToggling] = useState(false);

  const conv = useActiveConversation(effectiveTenantId, 'playground', {
    defaultWorkerId: workerId || 'default',
  });
  const {
    bootstrapping: conversationBootstrapping,
    createConversation,
    selectConversationById,
  } = conv;
  const activeProject = useMemo(
    () => (config?.projects ?? []).find((project) => project.project_id === projectId),
    [config?.projects, projectId]
  );
  const projectWorkerIds = useMemo(
    () => activeProject?.agents.map((agent) => agent.worker_id).filter(Boolean) ?? [],
    [activeProject]
  );
  const selectableWorkers = useMemo(
    () =>
      activeProject && projectWorkerIds.length > 0
        ? (config?.workers ?? []).filter((worker) => {
            const id = workerOptionId(worker);
            return projectWorkerIds.includes(id);
          })
        : (config?.workers ?? []),
    [activeProject, config?.workers, projectWorkerIds]
  );
  const firstProjectWorkerId = projectWorkerIds[0] ?? '';
  const workerBelongsToActiveProject = useCallback(
    (candidate: string) => {
      if (!activeProject || projectWorkerIds.length === 0) return true;
      const id = candidate.trim();
      return projectWorkerIds.includes(id);
    },
    [activeProject, projectWorkerIds]
  );
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: workerId,
    projectId,
    knowledgeScope,
    enabled: Boolean(conv.sessionId),
    onConversationActivity: conv.bumpRefresh,
    onConversationNotFound: conv.recoverMissingConversation,
    onSandboxArtifacts: (payload) => {
      const chat = conv.sessionId ?? '';
      const run = payload.sandbox_run_id?.trim() ?? '';
      const q = new URLSearchParams({ tab: 'files' });
      if (chat) q.set('chat', chat);
      if (run) q.set('run', run);
      router.push(`/sandbox?${q.toString()}`);
    },
  });

  useEffect(() => {
    writeLastProjectId(projectId);
    setKnowledgeScope((prev) => normalizeKnowledgeScope(prev, projectId));
  }, [projectId]);

  useEffect(() => {
    if (searchParams.get('new') !== '1' || !config || conversationBootstrapping) return;
    let cancelled = false;

    async function createRequestedConversation() {
      try {
        await createConversation();
        if (!cancelled) {
          setShowHistory(false);
          router.replace('/playground', { scroll: false });
        }
      } catch {
        if (!cancelled) {
          router.replace('/playground', { scroll: false });
        }
      }
    }

    void createRequestedConversation();
    return () => {
      cancelled = true;
    };
  }, [searchParams, config, conversationBootstrapping, createConversation, router]);

  useEffect(() => {
    const requestedConversation = searchParams.get('conversation') || '';
    if (!requestedConversation || !config || conversationBootstrapping) return;
    let cancelled = false;

    async function selectRequestedConversation() {
      try {
        await selectConversationById(requestedConversation);
        if (!cancelled) setShowHistory(false);
      } finally {
        if (!cancelled) {
          router.replace('/playground', { scroll: false });
        }
      }
    }

    void selectRequestedConversation();
    return () => {
      cancelled = true;
    };
  }, [searchParams, config, conversationBootstrapping, selectConversationById, router]);

  const loadConfig = useCallback(() => {
    const chatId = conv.sessionId ?? undefined;
    setConfigLoading(true);
    adminService
      .getPlaygroundConfig(
        chatId
          ? {
              chat_id: chatId,
              tenant_id: undefined,
            }
          : undefined
      )
      .then(async (c) => {
        setConfig(c);
        setConfigError(null);
        if (c.knowledge_scope) {
          setKnowledgeScope(normalizeKnowledgeScope(c.knowledge_scope, projectId));
        }
        const tenantId = (c.effective_tenant_id || profileTenantId || 'default').trim() || 'default';
        const fromServer = (c.selected_worker_id || '').trim();
        const ids = workerOptionIds(c.workers);
        const workerOk = (id: string) => Boolean(id && (ids.includes(id) || id === 'default'));
        let nextWorker = '';
        if (initialWorker && workerOk(initialWorker)) {
          nextWorker = initialWorker;
        } else if (fromServer && workerOk(fromServer)) {
          nextWorker = fromServer;
        } else if (chatId) {
          const stored = readStoredWorker(chatId);
          if (stored && workerOk(stored)) nextWorker = stored;
        }
        if (!nextWorker) {
          const lastWorker = readPlaygroundLastWorker(tenantId);
          if (lastWorker && workerOk(lastWorker)) nextWorker = lastWorker;
        }
        if (!nextWorker) {
          nextWorker = ids.includes('default') ? 'default' : ids[0] ?? 'default';
        }
        setWorkerId(nextWorker);
        writePlaygroundLastWorker(tenantId, nextWorker);

        if (chatId) {
          const lastLlm = readPlaygroundLastLlm(tenantId);
          const scope = c.llm?.scope;
          const serverProvider = (c.llm?.provider || '').trim();
          const serverModel = (c.llm?.model || '').trim();
          if (
            lastLlm &&
            (scope === 'env_bootstrap' || scope === 'runtime' || !serverModel) &&
            (serverProvider !== lastLlm.provider || serverModel !== lastLlm.model)
          ) {
            try {
              await adminService.setPlaygroundModel({
                chat_id: chatId,
                provider: lastLlm.provider,
                ...(lastLlm.model ? { model: lastLlm.model } : {}),
              });
              const refreshed = await adminService.getPlaygroundConfig({
                chat_id: chatId,
                tenant_id: undefined,
              });
              setConfig(refreshed);
            } catch {
              /* keep server config */
            }
          }
        }
      })
      .catch((err) => {
        setConfigError(err instanceof Error ? err.message : 'No se pudo cargar la configuración del playground');
      })
      .finally(() => setConfigLoading(false));
  }, [initialWorker, conv.sessionId, projectId, profileTenantId]);

  const persistKnowledgeScope = useCallback(
    async (nextScope: KnowledgeScope) => {
      const normalized = normalizeKnowledgeScope(nextScope, projectId);
      setKnowledgeScope(normalized);
      const chatId = conv.sessionId ?? '';
      if (!chatId) return;
      try {
        await adminService.setPlaygroundKnowledgeScope({
          chat_id: chatId,
          tenant_id: config?.effective_tenant_id,
          knowledge_scope: normalized,
          project_id: projectId || undefined,
        });
        loadConfig();
      } catch {
        /* keep local selection */
      }
    },
    [conv.sessionId, config?.effective_tenant_id, projectId, loadConfig]
  );

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    adminService
      .listKnowledgeSources()
      .then((sources) => {
        const indexed = sources.filter((s) => (s.chunk_count || 0) > 0).length;
        setIndexedKnowledgeSources(indexed);
      })
      .catch(() => setIndexedKnowledgeSources(0));
  }, [config?.effective_tenant_id]);

  useEffect(() => {
    if (workerId && chat.workerId !== workerId) {
      chat.setWorkerId(workerId);
    }
    // chat entero cambia cada render; solo sincronizar por workerIds.
  }, [workerId, chat.workerId, chat.setWorkerId]);

  const syncProjectWorkerSelection = useCallback(
    (nextWorker: string) => {
      const chatId = conv.sessionId;
      if (!chatId || !nextWorker.trim()) return;
      const tid = (config?.effective_tenant_id || 'default').trim() || 'default';
      void adminService
        .setPlaygroundWorker({
          chat_id: chatId,
          tenant_id: tid,
          worker_id: nextWorker.trim(),
        })
        .catch(() => undefined);
    },
    [config?.effective_tenant_id, conv.sessionId]
  );

  useEffect(() => {
    if (!activeProject || projectWorkerIds.length === 0) return;
    if (workerBelongsToActiveProject(workerId)) return;
    const nextWorker = firstProjectWorkerId;
    if (!nextWorker) return;
    // El worker actual no pertenece al proyecto: usar el primer agente asignado.
    setWorkerId(nextWorker);
    syncProjectWorkerSelection(nextWorker);
  }, [
    activeProject,
    firstProjectWorkerId,
    projectWorkerIds.length,
    syncProjectWorkerSelection,
    workerBelongsToActiveProject,
    workerId,
  ]);

  useEffect(() => {
    if (!workerId) return;
    adminService
      .getTemplate(workerId)
      .then((t) => {
        const sp = t.contents['system_prompt.md'];
        setSystemPreview(typeof sp === 'string' ? sp : '');
      })
      .catch(() => setSystemPreview(''));
  }, [workerId]);

  const [showHistory, setShowHistory] = useState(
    searchParams.get('new') !== '1' && !searchParams.get('conversation')
  );
  const isHistoryView = showHistory;

  useEffect(() => {
    setMainScrollEl(document.getElementById('admin-main-scroll'));
  }, []);

  useEffect(() => {
    const main = document.getElementById('admin-main-scroll');
    if (!main || typeof window === 'undefined') return;
    const mq = window.matchMedia('(max-width: 1023px)');
    const apply = () => {
      if (mq.matches && !isHistoryView) {
        main.classList.add('!overflow-hidden');
      } else {
        main.classList.remove('!overflow-hidden');
      }
    };
    apply();
    mq.addEventListener('change', apply);
    return () => {
      mq.removeEventListener('change', apply);
      main.classList.remove('!overflow-hidden');
    };
  }, [isHistoryView]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(min-width: 1024px)');
    const apply = () => {
      if (mq.matches) setPanelOpen(true);
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  const pageScroll = useScrollFabPair(mainScrollEl);
  const activeVaultPath = chat.vaultPath || config?.vault?.effective_path || '';
  const activeVaultScope = chat.vaultPath ? 'chat' : config?.vault?.scope;
  const handleSandboxToggle = useCallback(
    async (command: '/sandbox on' | '/sandbox off') => {
      if (!conv.sessionId || !workerId.trim()) {
        throw new Error('Sesión o worker no listos para sandbox');
      }
        setSandboxToggling(true);
      try {
        await adminService.playgroundChat({
          worker_id: workerId.trim(),
          message: command,
          chat_id: conv.sessionId,
          tenant_id: config?.effective_tenant_id,
          vault_db_path: activeVaultPath || undefined,
        });
      } finally {
        setSandboxToggling(false);
      }
    },
    [activeVaultPath, config?.effective_tenant_id, conv.sessionId, workerId]
  );
  const handleLogsToggle = useCallback(() => {
    setLogsPanelOpen((open) => !open);
  }, []);
  const playgroundComposeChips = useMemo(
    () =>
      conv.sessionId && workerId ? (
        <>
          {projectId ? (
            <span
              className="inline-flex max-w-[min(100%,12rem)] items-center rounded-full border border-gov-blue-200 bg-gov-blue-50 px-2 py-1 text-[10px] font-bold text-gov-blue-900 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan"
              title={projectId}
            >
              <span className="truncate">{activeProject?.name || projectId}</span>
            </span>
          ) : null}
          <PlaygroundRagProjectWarning
            projectId={projectId}
            knowledgeScope={knowledgeScope}
            indexedSourceCount={indexedKnowledgeSources}
            onOpenRouting={() => setSettingsModal('routing')}
          />
        </>
      ) : null,
    [
      activeProject?.name,
      conv.sessionId,
      indexedKnowledgeSources,
      knowledgeScope,
      projectId,
      workerId,
    ]
  );
  const selectWorker = useCallback(
    (next: string) => {
      setWorkerId(next);
      const tid = (config?.effective_tenant_id || profileTenantId || 'default').trim() || 'default';
      writePlaygroundLastWorker(tid, next);
      const chatId = conv.sessionId;
      if (chatId && next.trim()) {
        void adminService
          .setPlaygroundWorker({
            chat_id: chatId,
            tenant_id: tid,
            worker_id: next.trim(),
          })
          .catch(() => undefined);
        chat.setWorkerId(next.trim(), { persist: true });
      }
    },
    [chat.setWorkerId, config?.effective_tenant_id, conv.sessionId, profileTenantId]
  );
  const panelToggleTitle = panelOpen ? 'Ocultar panel de configuración' : 'Mostrar panel de configuración';

  const runSettingsPanel = (
    <Pm2LiveLogsProvider autoStart={logsPanelOpen}>
      <PlaygroundRunSettingsPanel
        config={config}
        workerId={workerId}
        activeVaultPath={activeVaultPath}
        activeVaultScope={activeVaultScope}
        workerLabel={
          workerOptionLabel(
            selectableWorkers.find((worker) => workerOptionId(worker) === workerId) ?? workerId
          ) || workerId || '—'
        }
        projectLabel={activeProject?.name || 'Todos los agentes'}
        knowledgeScopeLabel={knowledgeScopeLabel(knowledgeScope)}
        systemPreview={systemPreview}
        systemReady={Boolean(systemPreview.trim())}
        invalidWorkers={config?.workers_invalid ?? []}
        logsPanelOpen={logsPanelOpen}
        onLogsToggle={handleLogsToggle}
        logsControls={logsPanelOpen ? <Pm2LiveLogsControls variant="studio" /> : null}
        logsViewport={logsPanelOpen ? <Pm2LiveLogsViewport /> : null}
        onSandboxToggle={handleSandboxToggle}
        sandboxToggling={sandboxToggling}
        chatId={conv.sessionId || ''}
        tenantId={config?.effective_tenant_id}
        onOpen={setSettingsModal}
      />
    </Pm2LiveLogsProvider>
  );

  const settingsDialog = (
    <>
      {settingsModal === 'routing' && (
        <SettingsModal
          title="Contexto del chat"
          description="Proyecto, agente y alcance de conocimiento RAG."
          onClose={() => setSettingsModal(null)}
        >
          <ProjectAgentControls
            config={config}
            projectId={projectId}
            knowledgeScope={knowledgeScope}
            activeProject={activeProject}
            projectWorkerIds={projectWorkerIds}
            selectableWorkers={selectableWorkers}
            workerId={workerId}
            onProjectChange={(nextProjectId) => {
              setProjectId(nextProjectId);
              const nextProject = (config?.projects ?? []).find(
                (project) => project.project_id === nextProjectId
              );
              const nextProjectWorkers =
                nextProject?.agents.map((agent) => agent.worker_id).filter(Boolean) ?? [];
              if (nextProjectWorkers.length > 0) {
                const keepCurrent =
                  workerId.trim() && nextProjectWorkers.includes(workerId.trim());
                selectWorker(keepCurrent ? workerId : nextProjectWorkers[0]!);
                return;
              }
              // Sin agentes en el proyecto: no vaciar — loadConfig / lista global mantiene default.
              if (!workerId.trim()) {
                const ids = workerOptionIds(config?.workers);
                const fallback = ids.includes('default') ? 'default' : ids[0] ?? '';
                if (fallback) selectWorker(fallback);
              }
            }}
            onWorkerChange={selectWorker}
            onKnowledgeScopeChange={(scope) => void persistKnowledgeScope(scope)}
          />
        </SettingsModal>
      )}

      {settingsModal === 'model' && (
        <SettingsModal
          title="Model selection"
          description="Proveedor LLM (nube o MLX-Inference local). SLM opcional abajo es herramienta aparte."
          size="wide"
          onClose={() => setSettingsModal(null)}
        >
          {conv.sessionId ? (
            <div className="space-y-6">
              <div className="space-y-3">
                <SettingValue
                  label="LLM actual"
                  value={`${config?.llm?.provider || '—'} · ${config?.llm?.model || '—'}`}
                />
                <p className="text-xs font-black uppercase tracking-wider text-gov-gray-500">LLM</p>
                <ChatLlmSelectors
                  chatId={conv.sessionId}
                  tenantId={config?.effective_tenant_id || profileTenantId}
                  provider={config?.llm?.provider ?? ''}
                  model={config?.llm?.model ?? ''}
                  catalog={config?.catalog ?? []}
                  mlxInference={config?.slm}
                  onUpdated={loadConfig}
                  disabled={config?.authorized === false || chat.loading}
                  size="modal"
                />
              </div>
              <div className="space-y-3 border-t dark:border-dark-border pt-4">
                <SettingValue
                  label="SLM actual"
                  value={
                    config?.slm?.enabled
                      ? `${config.slm.model_short || config.slm.model} (${config.slm.mlx_status})`
                      : 'Ninguno'
                  }
                />
                <p className="text-xs font-black uppercase tracking-wider text-gov-gray-500">
                  SLM (opcional)
                </p>
                <ChatSlmSelector
                  chatId={conv.sessionId}
                  slm={config?.slm}
                  onUpdated={loadConfig}
                  disabled={config?.authorized === false || chat.loading}
                  size="modal"
                />
              </div>
            </div>
          ) : (
            <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
          )}
        </SettingsModal>
      )}

      {settingsModal === 'vault' && (
        <SettingsModal
          title="Base de datos de esta sesión"
          description="Archivo .duckdb que usa esta conversación para SQL, reglas y conocimiento (RAG)."
          onClose={() => setSettingsModal(null)}
        >
          {conv.sessionId ? (
            <ConversationVaultSelector
              chatId={conv.sessionId}
              tenantId={config?.effective_tenant_id}
              value={chat.vaultPath}
              effectivePath={activeVaultPath}
              scope={activeVaultScope}
              options={config?.vault_options}
              onChange={chat.setVaultPath}
              onUpdated={loadConfig}
              compact
            />
          ) : (
            <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
          )}
        </SettingsModal>
      )}

      {settingsModal === 'instructions' && (
        <SettingsModal
          title="System instructions"
          description="Prompt base del agente seleccionado."
          onClose={() => setSettingsModal(null)}
        >
          <MarkdownSnippetPanel
            content={systemPreview}
            emptyLabel="Sin system_prompt.md"
            maxHeightClass="max-h-72"
          />
          <Link
            href={`/templates/${workerId}?focus=system_prompt.md`}
            className="text-xs text-gov-blue-700 font-semibold mt-3 inline-flex items-center gap-1"
          >
            Editar comportamiento <ChevronRight size={12} />
          </Link>
        </SettingsModal>
      )}

      {settingsModal === 'commands' && (
        <SettingsModal
          title="Comandos"
          description="Atajos copiables para hablar con el agente."
          onClose={() => setSettingsModal(null)}
        >
          <ChatCommandsPanel />
        </SettingsModal>
      )}
    </>
  );

  return (
    <div className="flex flex-col lg:flex-row gap-3 min-h-0 h-full max-lg:h-[calc(100dvh-4rem)] max-lg:overflow-hidden w-full relative">
      <ScrollFabPair
        showScrollTop={pageScroll.showScrollTop}
        showScrollBottom={pageScroll.showScrollBottom}
        onScrollTop={() => pageScroll.scrollToTop('smooth')}
        onScrollBottom={() => pageScroll.scrollToBottom('smooth')}
      />

      {isHistoryView ? (
        <PlaygroundHistoryView
          tenantId={effectiveTenantId}
          workers={config?.workers}
          configLoading={configLoading}
          configError={configError}
          authHydrated={authHydrated}
          onRetryConfig={loadConfig}
          onSelectConversation={(id) => {
            void conv.selectConversationById(id).then(() => setShowHistory(false));
          }}
        />
      ) : (
        <>
      <div className="relative flex flex-1 flex-col min-w-0 min-h-0 h-[calc(100dvh-5.5rem)] max-h-[calc(100dvh-5.5rem)] lg:h-full lg:max-h-none bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setShowHistory(true)}
          className="absolute left-3 top-3 z-20 flex items-center gap-1.5 rounded-full border border-gov-blue-100 bg-white/90 px-2.5 py-2 text-[11px] font-black text-gov-blue-800 shadow-sm backdrop-blur hover:bg-gov-blue-50 dark:border-dark-border dark:bg-dark-surface/90 dark:text-dark-cyan dark:hover:bg-dark-bg"
          aria-label="Volver al historial"
        >
          <ArrowLeft size={14} />
          <span className="hidden sm:inline">Historial</span>
        </button>
        <div className="lg:hidden absolute right-3 top-3 z-20 flex items-center gap-2">
          <Link
            href={
              conv.sessionId
                ? `/sandbox?tab=files&chat=${encodeURIComponent(conv.sessionId)}`
                : '/sandbox'
            }
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-2 text-[11px] font-black shadow-sm backdrop-blur border-gov-blue-100 bg-white/90 text-gov-blue-800 dark:border-dark-border dark:bg-dark-surface/90 dark:text-dark-cyan`}
            aria-label="Abrir sandbox"
          >
            <FolderOpen size={14} />
            <span className="sr-only sm:not-sr-only">Sandbox</span>
          </Link>
          <button
            type="button"
            onClick={() => {
              setLogsPanelOpen((open) => {
                const next = !open;
                if (next) setPanelOpen(true);
                return next;
              });
            }}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-2 text-[11px] font-black shadow-sm backdrop-blur ${
              logsPanelOpen
                ? 'border-gov-blue-700 bg-gov-blue-700 text-white'
                : 'border-gov-blue-100 bg-white/90 text-gov-blue-800 dark:border-dark-border dark:bg-dark-surface/90 dark:text-dark-cyan'
            }`}
            aria-pressed={logsPanelOpen}
            aria-label="Logs PM2"
          >
            <Terminal size={14} />
            <span className="sr-only sm:not-sr-only">Logs</span>
          </button>
          <button
            type="button"
            onClick={() => setPanelOpen((open) => !open)}
            className="flex items-center gap-1.5 rounded-full border border-gov-blue-100 bg-white/90 px-2.5 py-2 text-[11px] font-black text-gov-blue-800 shadow-sm backdrop-blur dark:border-dark-border dark:bg-dark-surface/90 dark:text-dark-cyan"
            aria-expanded={panelOpen}
            aria-label={panelToggleTitle}
          >
            <Settings2 size={15} aria-hidden />
            <span className="sr-only sm:not-sr-only">Run settings</span>
          </button>
        </div>
        {conv.bootstrapping || !conv.sessionId ? (
          <p className="flex-1 flex items-center justify-center text-sm text-gov-gray-400 p-8">
            Cargando conversación…
          </p>
        ) : (
          <>
            <AdminChatPanel
            key={conv.sessionId}
            chatId={conv.sessionId}
            chat={chat}
            initialWorker={workerId}
            variant="full"
            showHeader={false}
            showStudioHeader
            showWorkerLink={false}
            composeLayout="studio"
            composeChips={playgroundComposeChips}
            conversationTitle={conv.conversationTitle}
            onRenameConversation={conv.renameConversation}
            emptyHint={
              workerId
                ? `Escribe un mensaje para hablar con ${workerId}`
                : 'Escribe un mensaje para hablar con …'
            }
            className="flex-1 lg:h-full min-h-0 border-0 rounded-none shadow-none"
          />
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => setPanelOpen((open) => !open)}
        className="hidden lg:flex fixed right-6 top-24 z-20 items-center justify-center px-2 py-3 rounded-l-2xl bg-white dark:bg-dark-surface border border-r-0 dark:border-dark-border shadow-md text-gov-blue-700 hover:bg-gov-gray-50 dark:hover:bg-dark-bg"
        aria-label={panelToggleTitle}
        title={panelToggleTitle}
      >
        {panelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
      </button>

      {panelOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 flex"
          role="dialog"
          aria-label="Configuración del Playground"
        >
          <button
            type="button"
            className="flex-1 bg-gov-blue-900/50 backdrop-blur-sm"
            aria-label="Cerrar configuración"
            onClick={() => setPanelOpen(false)}
          />
          <aside className="relative w-full max-w-[min(100vw,24rem)] min-w-0 h-full flex flex-col bg-white dark:bg-dark-surface border-l dark:border-dark-border shadow-xl">
            <div className="flex items-center justify-between gap-2 shrink-0 p-4 border-b dark:border-dark-border">
              <span className="text-sm font-medium text-gov-gray-900 dark:text-dark-text">
                Run settings
              </span>
              <button
                type="button"
                onClick={() => setPanelOpen(false)}
                className="p-2 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                aria-label="Cerrar"
              >
                <X size={18} />
              </button>
            </div>
            <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-4 space-y-3 overscroll-contain">
              {runSettingsPanel}
            </div>
          </aside>
        </div>
      )}

      <aside
        className={`hidden lg:flex shrink-0 flex-col min-h-0 overflow-hidden transition-[width,opacity] duration-300 ease-out ${
          panelOpen ? 'w-80 opacity-100' : 'w-0 max-w-0 opacity-0 pointer-events-none'
        }`}
        aria-hidden={!panelOpen}
      >
        <div className="flex h-full min-h-0 w-80 min-w-0 flex-col overflow-hidden rounded-2xl border border-gov-gray-200/90 bg-gov-gray-50/40 p-3 dark:border-dark-border dark:bg-dark-bg/60">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-gov-gray-200/80 pb-3 dark:border-dark-border">
            <h2 className="text-sm font-medium text-gov-gray-900 dark:text-dark-text">Run settings</h2>
            <Settings2 size={15} className="text-gov-gray-400 dark:text-dark-muted" aria-hidden />
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden pt-3">
            {runSettingsPanel}
          </div>
        </div>
      </aside>

      {settingsDialog}
        </>
      )}
    </div>
  );
}
