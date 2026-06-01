'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminService, type AdminConversation } from '@/services/adminService';
import {
  Settings2,
  Bot,
  ChevronDown,
  ChevronRight,
  Copy,
  PanelRightClose,
  PanelRightOpen,
  Terminal,
} from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { LlmProviderCatalog } from '@/components/chat/LlmProviderCatalog';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';
import { ScrollFabPair } from '@/components/shared/ScrollFabPair';
import { useScrollFabPair } from '@/components/shared/useScrollFabPair';
import { workerOptionId, workerOptionIds, workerOptionLabel } from '@/lib/workerOptions';
import type { FlyCommandEntry } from '@/types/admin';

const FREQUENT_CHAT_COMMANDS = new Set(['/team', '/vault', '/model', '/workers']);
type PlaygroundConfigSection = 'commands' | 'vault' | 'model' | 'instructions' | null;

export default function PlaygroundPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialWorker = searchParams.get('worker') || '';
  const initialProject = searchParams.get('project') || '';
  const [panelOpen, setPanelOpen] = useState(true);
  const [mainScrollEl, setMainScrollEl] = useState<HTMLElement | null>(null);
  const [systemPreview, setSystemPreview] = useState('');
  const [openConfigSection, setOpenConfigSection] = useState<PlaygroundConfigSection>('commands');
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [workerId, setWorkerId] = useState(initialWorker);
  const [projectId, setProjectId] = useState(initialProject);

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
      activeProject
        ? (config?.workers ?? []).filter((worker) => projectWorkerIds.includes(workerOptionId(worker)))
        : (config?.workers ?? []),
    [activeProject, config?.workers, projectWorkerIds]
  );

  const conv = useActiveConversation(config?.effective_tenant_id, 'playground');
  const {
    bootstrapping: conversationBootstrapping,
    createConversation,
    selectConversationById,
  } = conv;
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
        setWorkerId((prev) => {
          if (prev) return prev;
          const project = (c.projects ?? []).find((item) => item.project_id === initialProject);
          const ids = project?.agents?.length
            ? project.agents.map((agent) => agent.worker_id).filter(Boolean)
            : workerOptionIds(c.workers);
          if (initialWorker && ids.includes(initialWorker)) return initialWorker;
          if (ids.includes('default')) return 'default';
          return ids[0] ?? '';
        });
      })
      .catch(() => undefined);
  }, [initialWorker, initialProject, conv.sessionId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (workerId && chat.workerId !== workerId) {
      chat.setWorkerId(workerId);
    }
  }, [workerId, chat]);

  useEffect(() => {
    if (!activeProject) return;
    if (workerId && projectWorkerIds.includes(workerId)) return;
    setWorkerId(projectWorkerIds[0] ?? '');
  }, [activeProject, projectWorkerIds, workerId]);

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

  useEffect(() => {
    setMainScrollEl(document.getElementById('admin-main-scroll'));
  }, []);

  const pageScroll = useScrollFabPair(mainScrollEl);
  const isHistoryView = searchParams.get('view') === 'history';
  const activeVaultPath = chat.vaultPath || config?.vault?.effective_path || '';
  const activeVaultScope = chat.vaultPath ? 'chat' : config?.vault?.scope;
  const toggleConfigSection = useCallback((section: Exclude<PlaygroundConfigSection, null>) => {
    setOpenConfigSection((current) => (current === section ? null : section));
  }, []);
  const panelToggleTitle = panelOpen ? 'Ocultar panel de configuración' : 'Mostrar panel de configuración';

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[calc(100vh-8rem)] lg:h-[calc(100vh-8rem)] lg:min-h-0 lg:overflow-hidden relative">
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
      <div className="flex-1 flex flex-col min-w-0 min-h-[calc(100vh-8rem)] lg:min-h-0 lg:h-full bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-3 p-4 border-b dark:border-dark-border">
          <div>
            <h1 className="text-xl font-black dark:text-dark-text flex items-center gap-2">
              <Bot size={22} /> Playground
            </h1>
            {conv.conversationTitle?.trim() ? (
              <EditableConversationTitle
                value={conv.conversationTitle.trim()}
                onSave={conv.renameConversation}
                compact
                className="text-xs text-gov-gray-500 mt-0.5"
              />
            ) : (
              <p className="text-xs text-gov-gray-500 mt-0.5">Respuestas en vivo (SSE)</p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {(config?.projects?.length ?? 0) > 0 && (
              <>
                <label className="text-xs font-bold text-gov-gray-500">Proyecto</label>
                <select
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  className="text-sm px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg max-w-[240px]"
                >
                  <option value="">Sin proyecto</option>
                  {(config?.projects ?? []).map((project) => (
                    <option key={project.project_id} value={project.project_id}>
                      {project.name} ({project.agents.length})
                    </option>
                  ))}
                </select>
              </>
            )}
            <label className="text-xs font-bold text-gov-gray-500">Agente</label>
            <select
              value={workerId}
              onChange={(e) => setWorkerId(e.target.value)}
              className="text-sm px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg max-w-[240px]"
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
            <Link
              href={`/templates/${workerId}`}
              className="text-xs text-gov-blue-700 font-semibold flex items-center gap-1"
            >
              Editar <ChevronRight size={12} />
            </Link>
          </div>
        </header>
        {config && (config.workers_invalid?.length ?? 0) > 0 && (
          <p className="mx-4 mb-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-3 py-2 rounded-xl">
            Agentes no disponibles: {(config.workers_invalid ?? []).join(', ')}.
          </p>
        )}
        {activeProject && (
          <p className="mx-4 mb-2 text-xs text-gov-blue-800 dark:text-dark-cyan bg-gov-cyan-50 dark:bg-dark-bg border border-gov-cyan-200 dark:border-dark-border px-3 py-2 rounded-xl">
            Proyecto activo: <strong>{activeProject.name}</strong>. Verás solo los agentes de este proyecto.
          </p>
        )}
        {conv.bootstrapping || !conv.sessionId ? (
          <p className="flex-1 flex items-center justify-center text-sm text-gov-gray-400 p-8">
            Cargando conversación…
          </p>
        ) : (
          <AdminChatPanel
            key={`${conv.sessionId}-${projectId}-${workerId}`}
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

      <aside
        className={`shrink-0 min-h-0 overflow-hidden transition-[width,opacity] duration-300 ease-out ${
          panelOpen
            ? 'w-full lg:w-80 lg:h-full opacity-100'
            : 'w-0 max-w-0 opacity-0 pointer-events-none lg:hidden'
        }`}
        aria-hidden={!panelOpen}
      >
        <div className="w-full lg:w-80 h-full min-h-0 flex flex-col">
          <div className="flex items-center justify-between gap-2 shrink-0 pb-2">
            <span className="text-xs font-bold uppercase text-gov-gray-500 tracking-wide">
              Configuración
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1 space-y-3">
            <CurrentConfigSummary
                config={config}
                activeVaultPath={activeVaultPath}
                activeVaultScope={activeVaultScope}
                workerLabel={workerId || '—'}
            />
            <ConfigAccordionSection
              title="Comandos"
              description="Comandos del chat"
              open={openConfigSection === 'commands'}
              onToggle={() => toggleConfigSection('commands')}
            >
              <ChatCommandsPanel />
            </ConfigAccordionSection>
            <ConfigAccordionSection
              title="Cambiar bóveda"
              description="DuckDB de esta conversación"
              open={openConfigSection === 'vault'}
              onToggle={() => toggleConfigSection('vault')}
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
                />
              ) : (
                <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
              )}
            </ConfigAccordionSection>
            <ConfigAccordionSection
              title="Cambiar modelo"
              description="Proveedor y modelo LLM"
              open={openConfigSection === 'model'}
              onToggle={() => toggleConfigSection('model')}
            >
              {conv.sessionId ? (
                <LlmProviderCatalog
                  chatId={conv.sessionId}
                  catalog={config?.catalog ?? []}
                  onUpdated={loadConfig}
                />
              ) : (
                <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
              )}
            </ConfigAccordionSection>
            <ConfigAccordionSection
              title="Instrucciones"
              description="Comportamiento del agente"
              open={openConfigSection === 'instructions'}
              onToggle={() => toggleConfigSection('instructions')}
            >
              <MarkdownSnippetPanel
                content={systemPreview}
                emptyLabel="Sin system_prompt.md"
                maxHeightClass="max-h-48"
              />
              <Link
                href={`/templates/${workerId}?focus=system_prompt.md`}
                className="text-xs text-gov-blue-700 font-semibold mt-2 inline-block"
              >
                Editar comportamiento →
              </Link>
            </ConfigAccordionSection>
          </div>
        </div>
      </aside>
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
                <Link
                  href={`/playground?conversation=${encodeURIComponent(conversation.session_id)}`}
                  className="block rounded-2xl border dark:border-dark-border p-4 hover:border-gov-blue-300 hover:bg-gov-blue-50/50 dark:hover:bg-dark-bg transition-colors"
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
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function CurrentConfigSummary({
  config,
  activeVaultPath,
  activeVaultScope,
  workerLabel,
}: {
  config: Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null;
  activeVaultPath: string;
  activeVaultScope?: string;
  workerLabel: string;
}) {
  return (
    <section className="sticky top-0 z-10 rounded-3xl border border-gov-blue-100 dark:border-dark-border bg-white/95 dark:bg-dark-surface/95 p-4 shadow-sm backdrop-blur space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-black text-sm flex items-center gap-2 dark:text-dark-text">
            <Settings2 size={18} className="text-gov-blue-700 dark:text-dark-cyan" />
            Estado actual
          </h2>
          <p className="text-[10px] text-gov-gray-500 mt-1">
            Lo esencial de esta conversación.
          </p>
        </div>
        <span className="rounded-full bg-emerald-50 dark:bg-emerald-950/30 px-2 py-1 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
          Activo
        </span>
      </div>

      <div className="grid gap-2">
        <SummaryChip label="Modelo" value={config?.llm?.model || '—'} />
        <SummaryChip label="DuckDB" value={activeVaultPath || '—'} mono highlight={activeVaultScope === 'chat'} />
        <SummaryChip label="Agente" value={workerLabel} />
      </div>

      {config?.llm?.scope === 'chat' && (
        <p className="text-[10px] text-gov-blue-700 dark:text-dark-cyan">
          Modelo fijado para esta conversación.
        </p>
      )}
      {activeVaultScope === 'chat' && (
        <p className="text-[10px] text-gov-blue-700 dark:text-dark-cyan">
          DuckDB fijada para esta conversación (no por worker).
        </p>
      )}
    </section>
  );
}

function SummaryChip({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-2xl bg-gov-gray-50 dark:bg-dark-bg px-3 py-2">
      <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-500">{label}</p>
      <p
        className={`text-xs truncate ${mono ? 'font-mono' : 'font-semibold'} ${
          highlight ? 'text-gov-blue-800 dark:text-dark-cyan' : 'text-gov-gray-800 dark:text-dark-text'
        }`}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}

function ConfigAccordionSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string;
  description: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-gov-gray-50 dark:hover:bg-dark-bg transition-colors"
        aria-expanded={open}
      >
        <span className="min-w-0">
          <span className="font-bold text-sm dark:text-dark-text">{title}</span>
          <span className="block text-xs text-gov-gray-500 mt-1">{description}</span>
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-gov-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </section>
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

