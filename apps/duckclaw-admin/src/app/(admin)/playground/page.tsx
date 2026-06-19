'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminService, type AdminConversation } from '@/services/adminService';
import {
  Settings2,
  Bot,
  ChevronRight,
  Copy,
  Brain,
  Database,
  FileText,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  SlidersHorizontal,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { ChatLlmSelectors } from '@/components/chat/ChatLlmSelectors';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';
import { ScrollFabPair } from '@/components/shared/ScrollFabPair';
import { useScrollFabPair } from '@/components/shared/useScrollFabPair';
import { workerOptionId, workerOptionIds, workerOptionLabel } from '@/lib/workerOptions';
import { SessionDatabaseChip } from '@/components/playground/SessionDatabaseChip';
import type { FlyCommandEntry } from '@/types/admin';

const FREQUENT_CHAT_COMMANDS = new Set(['/team', '/vault', '/model', '/workers']);
type PlaygroundConfig = Awaited<ReturnType<typeof adminService.getPlaygroundConfig>>;
type PlaygroundSettingsModal = 'commands' | 'vault' | 'model' | 'instructions' | 'routing' | null;

export default function PlaygroundPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialWorker = searchParams.get('worker') || '';
  const initialProject = searchParams.get('project') || '';
  const [panelOpen, setPanelOpen] = useState(false);
  const [mainScrollEl, setMainScrollEl] = useState<HTMLElement | null>(null);
  const [systemPreview, setSystemPreview] = useState('');
  const [settingsModal, setSettingsModal] = useState<PlaygroundSettingsModal>(null);
  const [config, setConfig] = useState<PlaygroundConfig | null>(null);
  const [workerId, setWorkerId] = useState(initialWorker);
  const [projectId, setProjectId] = useState(initialProject);
  const [defaultsSaving, setDefaultsSaving] = useState(false);
  const [defaultsMsg, setDefaultsMsg] = useState<string | null>(null);

  const conv = useActiveConversation(config?.effective_tenant_id, 'playground');
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
    enabled: Boolean(conv.sessionId),
    onConversationActivity: conv.bumpRefresh,
  });

  useEffect(() => {
    if (searchParams.get('new') !== '1' || !config || conversationBootstrapping) return;
    let cancelled = false;

    async function createRequestedConversation() {
      try {
        await createConversation();
        if (!cancelled) {
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
    adminService
      .getPlaygroundConfig(
        chatId
          ? {
              chat_id: chatId,
              tenant_id: undefined,
            }
          : undefined
      )
      .then((c) => {
        setConfig(c);
        const fromServer = (c.selected_worker_id || '').trim();
        const ids = workerOptionIds(c.workers);
        let nextWorker = ids[0] ?? '';
        if (initialWorker && ids.includes(initialWorker)) {
          nextWorker = initialWorker;
        } else if (fromServer && ids.includes(fromServer)) {
          nextWorker = fromServer;
        } else if (ids.includes('default')) {
          nextWorker = 'default';
        }
        setWorkerId(nextWorker);
      })
      .catch(() => undefined);
  }, [initialWorker, conv.sessionId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (workerId && chat.workerId !== workerId) {
      chat.setWorkerId(workerId);
    }
  }, [workerId, chat]);

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

  const isHistoryView = searchParams.get('view') === 'history';

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
  const selectWorker = useCallback(
    (next: string) => {
      setWorkerId(next);
      const chatId = conv.sessionId;
      if (chatId && next.trim()) {
        const tid = (config?.effective_tenant_id || 'default').trim() || 'default';
        void adminService
          .setPlaygroundWorker({
            chat_id: chatId,
            tenant_id: tid,
            worker_id: next.trim(),
          })
          .catch(() => undefined);
      }
    },
    [config?.effective_tenant_id, conv.sessionId]
  );
  const savePlaygroundDefaults = useCallback(async () => {
    if (!config) return;
    setDefaultsSaving(true);
    setDefaultsMsg(null);
    try {
      await adminService.patchRuntimeSettings([
        { domain: 'llm', key: 'provider', value: config.llm?.provider || '', scope: 'actor' },
        { domain: 'llm', key: 'model', value: config.llm?.model || '', scope: 'actor' },
        { domain: 'llm', key: 'base_url', value: config.llm?.base_url || '', scope: 'actor' },
        { domain: 'playground', key: 'default_worker_id', value: workerId || '', scope: 'actor' },
        {
          domain: 'playground',
          key: 'default_vault_db_path',
          value: activeVaultPath || '',
          scope: 'actor',
        },
      ]);
      setDefaultsMsg('Defaults guardados en DuckDB.');
      loadConfig();
    } catch (e) {
      setDefaultsMsg(e instanceof Error ? e.message : 'No se pudieron guardar defaults');
    } finally {
      setDefaultsSaving(false);
    }
  }, [activeVaultPath, config, loadConfig, workerId]);
  const panelToggleTitle = panelOpen ? 'Ocultar panel de configuración' : 'Mostrar panel de configuración';

  const runSettingsPanel = (
    <RunSettingsCard
      config={config}
      activeVaultPath={activeVaultPath}
      activeVaultScope={activeVaultScope}
      workerLabel={
        workerOptionLabel(
          selectableWorkers.find((worker) => workerOptionId(worker) === workerId) ?? workerId
        ) || workerId || '—'
      }
      projectLabel={activeProject?.name || 'Todos los agentes'}
      systemReady={Boolean(systemPreview.trim())}
      invalidWorkers={config?.workers_invalid ?? []}
      defaultsSaving={defaultsSaving}
      defaultsMsg={defaultsMsg}
      onSaveDefault={savePlaygroundDefaults}
      onOpen={setSettingsModal}
    />
  );

  const settingsDialog = (
    <>
      {settingsModal === 'routing' && (
        <SettingsModal
          title="Configurar proyecto y agente"
          description="Selecciona contexto sin ensuciar la superficie del chat."
          onClose={() => setSettingsModal(null)}
        >
          <ProjectAgentControls
            config={config}
            projectId={projectId}
            activeProject={activeProject}
            projectWorkerIds={projectWorkerIds}
            selectableWorkers={selectableWorkers}
            workerId={workerId}
            onProjectChange={(nextProjectId) => {
              setProjectId(nextProjectId);
              setWorkerId('');
            }}
            onWorkerChange={selectWorker}
          />
        </SettingsModal>
      )}

      {settingsModal === 'model' && (
        <SettingsModal
          title="Modelo"
          description="Proveedor y modelo LLM de esta conversación."
          onClose={() => setSettingsModal(null)}
        >
          {conv.sessionId ? (
            <div className="space-y-3">
              <SettingValue label="Actual" value={`${config?.llm?.provider || '—'} · ${config?.llm?.model || '—'}`} />
              <ChatLlmSelectors
                chatId={conv.sessionId}
                provider={config?.llm?.provider ?? ''}
                model={config?.llm?.model ?? ''}
                catalog={config?.catalog ?? []}
                onUpdated={loadConfig}
                disabled={config?.authorized === false || chat.loading}
                compact
              />
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
    <div className="flex flex-col lg:flex-row gap-4 min-h-0 max-lg:h-[calc(100dvh-4rem)] max-lg:overflow-hidden lg:h-[calc(100vh-8rem)] lg:min-h-0 lg:overflow-hidden relative -mx-4 px-4 md:mx-0 md:px-0">
      <ScrollFabPair
        showScrollTop={pageScroll.showScrollTop}
        showScrollBottom={pageScroll.showScrollBottom}
        onScrollTop={() => pageScroll.scrollToTop('smooth')}
        onScrollBottom={() => pageScroll.scrollToBottom('smooth')}
      />

      {isHistoryView ? (
        <PlaygroundHistoryView tenantId={config?.effective_tenant_id} />
      ) : (
        <>
      <div className="relative flex-1 flex flex-col min-w-0 h-[calc(100dvh-5.5rem)] max-h-[calc(100dvh-5.5rem)] lg:h-full lg:max-h-none bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setPanelOpen((open) => !open)}
          className="lg:hidden absolute right-3 top-3 z-20 flex items-center gap-1.5 rounded-full border border-gov-blue-100 bg-white/90 px-3 py-2 text-[11px] font-black text-gov-blue-800 shadow-sm backdrop-blur dark:border-dark-border dark:bg-dark-surface/90 dark:text-dark-cyan"
          aria-expanded={panelOpen}
          aria-label={panelToggleTitle}
        >
          <Settings2 size={15} aria-hidden />
          Run settings
        </button>
        {conv.bootstrapping || !conv.sessionId ? (
          <p className="flex-1 flex items-center justify-center text-sm text-gov-gray-400 p-8">
            Cargando conversación…
          </p>
        ) : (
          <>
            <SessionDatabaseChip
              path={activeVaultPath}
              scope={activeVaultScope}
              onConfigure={() => setSettingsModal('vault')}
            />
            <AdminChatPanel
            key={`${conv.sessionId}-${workerId}`}
            chatId={conv.sessionId}
            chat={chat}
            initialWorker={workerId}
            variant="full"
            showHeader={false}
            showWorkerLink={false}
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
          <aside className="relative w-full max-w-sm h-full min-h-0 flex flex-col bg-white dark:bg-dark-surface border-l dark:border-dark-border shadow-xl">
            <div className="flex items-center justify-between gap-2 shrink-0 p-4 border-b dark:border-dark-border">
              <span className="text-xs font-bold uppercase text-gov-gray-500 tracking-wide">
                Configuración
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
            <div className="min-h-0 flex-1 overflow-y-auto p-4 space-y-3 overscroll-contain">
              {runSettingsPanel}
            </div>
          </aside>
        </div>
      )}

      <aside
        className={`hidden lg:flex shrink-0 min-h-0 overflow-hidden transition-[width,opacity] duration-300 ease-out ${
          panelOpen ? 'w-80 h-full opacity-100' : 'w-0 max-w-0 opacity-0 pointer-events-none'
        }`}
        aria-hidden={!panelOpen}
      >
        <div className="w-80 h-full min-h-0 flex flex-col">
          <div className="flex items-center justify-between gap-2 shrink-0 pb-2">
            <span className="text-xs font-bold uppercase text-gov-gray-500 tracking-wide">
              Run settings
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1 space-y-3">{runSettingsPanel}</div>
        </div>
      </aside>

      {settingsDialog}
        </>
      )}
    </div>
  );
}
function formatConversationTime(iso: string): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso.slice(0, 16);
  const mins = Math.floor((Date.now() - t) / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `hace ${days}d`;
  return new Date(t).toLocaleDateString();
}
function uniqueConversationsBySession(conversations: AdminConversation[]): AdminConversation[] {
  const seen = new Set<string>();
  return conversations.filter((conversation) => {
    if (seen.has(conversation.session_id)) return false;
    seen.add(conversation.session_id);
    return true;
  });
}

function PlaygroundHistoryView({ tenantId }: { tenantId?: string }) {
  const [conversations, setConversations] = useState<AdminConversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const uniqueConversations = useMemo(
    () => uniqueConversationsBySession(conversations),
    [conversations]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminService.listConversations({ tenant_id: tenantId, section: 'playground', limit: 80 })
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

    return () => {
      cancelled = true;
    };
  }, [tenantId]);

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
      <div className="h-full min-h-0 overflow-y-auto p-4">
        {loading && (
          <p className="text-sm text-gov-gray-400 text-center py-10">Cargando historial…</p>
        )}
        {error && <p className="text-sm text-red-600 text-center py-10">{error}</p>}
        {!loading && !error && uniqueConversations.length === 0 && (
          <div className="rounded-3xl border border-dashed dark:border-dark-border p-10 text-center">
            <p className="font-bold dark:text-dark-text">Sin conversaciones</p>
            <p className="text-sm text-gov-gray-500 mt-1">Crea una conversación para verla aquí.</p>
          </div>
        )}
        {!loading && !error && uniqueConversations.length > 0 && (
          <ul className="grid gap-2">
            {uniqueConversations.map((conversation) => (
              <li key={conversation.session_id}>
                <div className="flex items-stretch gap-2 rounded-2xl border dark:border-dark-border p-3 hover:border-gov-blue-300 hover:bg-gov-blue-50/50 dark:hover:bg-dark-bg transition-colors">
                  <Link
                    href={`/playground?conversation=${encodeURIComponent(conversation.session_id)}`}
                    className="min-w-0 flex-1"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-bold truncate dark:text-dark-text">
                          {conversation.title || conversation.session_id}
                        </p>
                        <p className="text-xs text-gov-gray-500 mt-1 line-clamp-2">
                          {conversation.last_message_preview || 'Sin mensajes todavía'}
                        </p>
                      </div>
                      <span className="text-[10px] font-black uppercase tracking-wide text-gov-gray-400 shrink-0">
                        {formatConversationTime(conversation.updated_at)}
                      </span>
                    </div>
                    <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-400 mt-2">
                      {conversation.last_worker_id || 'sin worker'} · {conversation.message_count} mensajes
                    </p>
                  </Link>
                  <button
                    type="button"
                    onClick={() => void deleteHistoryConversation(conversation)}
                    disabled={deletingSessionId === conversation.session_id}
                    className="shrink-0 self-center rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-50 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                    aria-label={`Eliminar conversación ${conversation.title || conversation.session_id}`}
                  >
                    <Trash2 size={15} aria-hidden />
                    <span className="sr-only">Eliminar</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function RunSettingsCard({
  config,
  activeVaultPath,
  activeVaultScope,
  workerLabel,
  projectLabel,
  systemReady,
  invalidWorkers,
  defaultsSaving,
  defaultsMsg,
  onSaveDefault,
  onOpen,
}: {
  config: PlaygroundConfig | null;
  activeVaultPath: string;
  activeVaultScope?: string;
  workerLabel: string;
  projectLabel: string;
  systemReady: boolean;
  invalidWorkers: string[];
  defaultsSaving: boolean;
  defaultsMsg: string | null;
  onSaveDefault: () => void;
  onOpen: (modal: Exclude<PlaygroundSettingsModal, null>) => void;
}) {
  return (
    <section className="sticky top-0 z-10 rounded-[1.75rem] border border-gov-blue-100 bg-white/95 p-3 shadow-sm backdrop-blur dark:border-dark-border dark:bg-dark-surface/95">
      <div className="flex items-start justify-between gap-3 px-1">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-black dark:text-dark-text">
            <SlidersHorizontal size={18} className="text-gov-blue-700 dark:text-dark-cyan" />
            Run settings
          </h2>
          <p className="mt-1 text-[10px] text-gov-gray-500">
            Control de conversación, sin ocupar chat.
          </p>
        </div>
        <span className="rounded-full bg-emerald-50 dark:bg-emerald-950/30 px-2 py-1 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
          Activo
        </span>
      </div>

      <div className="mt-3 grid gap-2">
        <RunSettingButton
          icon={<Brain size={16} aria-hidden />}
          title="Modelo"
          value={config?.llm?.model || '—'}
          detail={config?.llm?.provider || 'Proveedor LLM'}
          onClick={() => onOpen('model')}
        />
        <RunSettingButton
          icon={<Database size={16} aria-hidden />}
          title="Base de datos"
          value={activeVaultPath || '—'}
          detail={activeVaultScope === 'chat' ? 'Por conversación' : 'Misma para RAG y SQL'}
          mono
          onClick={() => onOpen('vault')}
        />
        <RunSettingButton
          icon={<Settings2 size={16} aria-hidden />}
          title="Proyecto"
          value={projectLabel}
          detail="Filtro de agentes"
          onClick={() => onOpen('routing')}
        />
        <RunSettingButton
          icon={<Bot size={16} aria-hidden />}
          title="Agente"
          value={workerLabel}
          detail="Worker de esta conversación"
          onClick={() => onOpen('routing')}
        />
        <RunSettingButton
          icon={<FileText size={16} aria-hidden />}
          title="System instructions"
          value={systemReady ? 'Cargado' : 'Sin prompt'}
          detail="Comportamiento del agente"
          onClick={() => onOpen('instructions')}
        />
        <RunSettingButton
          icon={<MessageSquareText size={16} aria-hidden />}
          title="Comandos"
          value="Atajos del chat"
          detail="/model · /vault · /workers"
          onClick={() => onOpen('commands')}
        />
      </div>

      {invalidWorkers.length > 0 && (
        <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Agentes no disponibles: {invalidWorkers.join(', ')}.
        </p>
      )}

      <div className="mt-3 rounded-2xl border border-gov-blue-100 bg-gov-blue-50/70 p-3 dark:border-dark-border dark:bg-dark-bg">
        <button
          type="button"
          onClick={onSaveDefault}
          disabled={!config || defaultsSaving}
          className="w-full rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
        >
          {defaultsSaving ? 'Guardando…' : 'Guardar como default'}
        </button>
        {defaultsMsg && (
          <p className="mt-2 text-[10px] font-semibold text-gov-blue-700 dark:text-dark-cyan">
            {defaultsMsg}
          </p>
        )}
      </div>
    </section>
  );
}

function RunSettingButton({
  icon,
  title,
  value,
  detail,
  mono,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  detail: string;
  mono?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 rounded-2xl bg-gov-gray-50 px-3 py-3 text-left transition-colors hover:bg-gov-blue-50 dark:bg-dark-bg dark:hover:bg-dark-border/50"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-gov-blue-700 shadow-sm dark:bg-dark-surface dark:text-dark-cyan">
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-bold text-gov-gray-500">{title}</span>
        <span
          className={`mt-0.5 block truncate text-sm font-black text-gov-gray-900 dark:text-dark-text ${
            mono ? 'font-mono text-xs' : ''
          }`}
          title={value}
        >
          {value}
        </span>
        <span className="mt-0.5 block truncate text-[10px] text-gov-gray-500" title={detail}>
          {detail}
        </span>
      </span>
      <ChevronRight
        size={16}
        className="shrink-0 text-gov-gray-300 transition-transform group-hover:translate-x-0.5 group-hover:text-gov-blue-600"
        aria-hidden
      />
    </button>
  );
}

function SettingsModal({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-gov-blue-950/40 p-3 backdrop-blur-sm sm:items-center">
      <button
        type="button"
        className="absolute inset-0"
        aria-label="Cerrar modal"
        onClick={onClose}
      />
      <section
        className="relative z-10 flex max-h-[min(760px,92dvh)] w-full max-w-md flex-col overflow-hidden rounded-[2rem] border border-gov-blue-100 bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="flex items-start justify-between gap-3 border-b border-gov-gray-100 p-4 dark:border-dark-border">
          <div className="min-w-0">
            <h3 className="text-base font-black dark:text-dark-text">{title}</h3>
            <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </section>
    </div>
  );
}

function SettingValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-gov-gray-50 px-3 py-2 dark:bg-dark-bg">
      <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-500">{label}</p>
      <p className="mt-0.5 truncate text-sm font-semibold dark:text-dark-text" title={value}>
        {value}
      </p>
    </div>
  );
}

function ProjectAgentControls({
  config,
  projectId,
  activeProject,
  projectWorkerIds,
  selectableWorkers,
  workerId,
  onProjectChange,
  onWorkerChange,
}: {
  config: PlaygroundConfig | null;
  projectId: string;
  activeProject?: NonNullable<PlaygroundConfig['projects']>[number];
  projectWorkerIds: string[];
  selectableWorkers: NonNullable<PlaygroundConfig['workers']>;
  workerId: string;
  onProjectChange: (projectId: string) => void;
  onWorkerChange: (workerId: string) => void;
}) {
  return (
    <div className="space-y-4">
      {(config?.projects?.length ?? 0) > 0 && (
        <label className="block space-y-1.5">
          <span className="text-xs font-bold text-gov-gray-500">Proyecto</span>
          <select
            value={projectId}
            onChange={(e) => onProjectChange(e.target.value)}
            className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            <option value="">Todos los agentes</option>
            {(config?.projects ?? []).map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block space-y-1.5">
        <span className="text-xs font-bold text-gov-gray-500">
          {activeProject ? 'Agente guía' : 'Agente'}
        </span>
        <select
          value={workerId}
          onChange={(e) => onWorkerChange(e.target.value)}
          className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
        >
          {selectableWorkers.map((w) => {
            const id = workerOptionId(w);
            const label = workerOptionLabel(w);
            return (
              <option key={id} value={id}>
                {label}
              </option>
            );
          })}
        </select>
      </label>

      <p className="rounded-2xl border border-gov-blue-100 bg-gov-blue-50/70 p-3 text-xs text-gov-blue-800 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan">
        {activeProject
          ? projectWorkerIds.length > 0
            ? `Proyecto ${activeProject.name}: solo agentes asignados.`
            : `Proyecto ${activeProject.name}: sin agentes asignados, se muestran todos.`
          : 'Sin filtro de proyecto.'}
      </p>

      {workerId && (
        <Link
          href={`/templates/${workerId}`}
          className="inline-flex items-center gap-1 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
        >
          Editar agente <ChevronRight size={12} />
        </Link>
      )}
    </div>
  );
}

function ChatCommandsPanel() {
  const [showAll, setShowAll] = useState(false);
  const [commands, setCommands] = useState<FlyCommandEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminService
      .listFlyCommands()
      .then((res) => {
        if (!cancelled) setCommands(res.commands ?? []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudieron cargar los comandos');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const frequentCommands = commands.filter((command) =>
    FREQUENT_CHAT_COMMANDS.has(command.cmd.trim().split(/\s+/)[0] ?? '')
  );
  const defaultCommands = frequentCommands.length > 0 ? frequentCommands : commands.slice(0, 4);
  const visibleCommands = showAll ? commands : defaultCommands;
  const canExpand = commands.length > defaultCommands.length;

  const copyCommand = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(cmd);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="space-y-3">
          <p className="text-xs text-gov-gray-500 flex items-center gap-2">
            <Terminal size={14} />
            Comandos del chat para usar dentro del Playground.
          </p>
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-black uppercase tracking-wide text-gov-gray-500">
              Comandos frecuentes
            </p>
            {canExpand && (
              <button
                type="button"
                onClick={() => setShowAll((value) => !value)}
                className="text-xs font-bold text-gov-blue-700 dark:text-dark-cyan"
              >
                {showAll ? 'Ver frecuentes' : 'Ver todos'}
              </button>
            )}
          </div>

          {error && (
            <p className="text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 rounded-xl p-3">
              {error}
            </p>
          )}

          <div className="space-y-2">
            {visibleCommands.map((command) => (
              <button
                key={command.cmd}
                type="button"
                onClick={() => void copyCommand(command.cmd)}
                className="w-full text-left rounded-2xl border dark:border-dark-border p-3 hover:border-gov-blue-400 hover:bg-gov-blue-50/50 dark:hover:bg-dark-bg transition-colors"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    <span className="block font-mono text-xs font-black text-gov-blue-700 dark:text-dark-cyan truncate">
                      {command.cmd}
                    </span>
                    <span className="block text-xs text-gov-gray-500 mt-1">
                      {command.description}
                    </span>
                  </span>
                  <Copy size={14} className="text-gov-gray-400 shrink-0 mt-0.5" />
                </span>
                {copied === command.cmd && (
                  <span className="block text-[10px] font-bold text-emerald-700 dark:text-emerald-400 mt-2">
                    Copiado
                  </span>
                )}
              </button>
            ))}
            {!error && visibleCommands.length === 0 && (
              <p className="text-xs text-gov-gray-500 rounded-xl border border-dashed dark:border-dark-border p-3">
                Sin comandos disponibles por ahora.
              </p>
            )}
          </div>
    </div>
  );
}
