'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import {
  Settings2,
  Bot,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { ConversationInbox } from '@/components/chat/ConversationInbox';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { PanelToggleButton } from '@/components/layout/PanelToggleButton';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { LlmProviderCatalog } from '@/components/chat/LlmProviderCatalog';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';
import { ScrollFabPair } from '@/components/shared/ScrollFabPair';
import { useScrollFabPair } from '@/components/shared/useScrollFabPair';
import { workerOptionId, workerOptionIds, workerOptionLabel } from '@/lib/workerOptions';

export default function PlaygroundPage() {
  const searchParams = useSearchParams();
  const initialWorker = searchParams.get('worker') || '';
  const initialProject = searchParams.get('project') || '';
  const [panelOpen, setPanelOpen] = useState(true);
  const [mainScrollEl, setMainScrollEl] = useState<HTMLElement | null>(null);
  const [systemPreview, setSystemPreview] = useState('');
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
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: workerId,
    projectId,
    enabled: Boolean(conv.sessionId),
    onConversationActivity: conv.bumpRefresh,
  });

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

  const activeCatalog = config?.catalog?.find((c) => c.active);

  useEffect(() => {
    setMainScrollEl(document.getElementById('admin-main-scroll'));
  }, []);

  const pageScroll = useScrollFabPair(mainScrollEl);

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[calc(100vh-8rem)] lg:h-[calc(100vh-8rem)] lg:min-h-0 lg:overflow-hidden relative">
      <ScrollFabPair
        showScrollTop={pageScroll.showScrollTop}
        showScrollBottom={pageScroll.showScrollBottom}
        onScrollTop={() => pageScroll.scrollToTop('smooth')}
        onScrollBottom={() => pageScroll.scrollToBottom('smooth')}
      />
      {conv.sessionId && (
        <ConversationInbox
          tenantId={config?.effective_tenant_id}
          defaultSectionFilter=""
          activeSessionId={conv.sessionId}
          refreshToken={conv.refreshToken}
          onSelect={(id, meta) => conv.selectConversation(id, meta?.title)}
          onTitleRenamed={(_id, title) => conv.syncConversationTitle(title)}
          className="hidden md:flex lg:h-full lg:max-h-full rounded-3xl border dark:border-dark-border overflow-hidden bg-white dark:bg-dark-surface"
        />
      )}

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
        {config &&
          (config.team_hint || (config.workers_invalid?.length ?? 0) > 0) && (
          <p className="mx-4 mb-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-3 py-2 rounded-xl">
            {config.team_hint}
            {(config.workers_invalid?.length ?? 0) > 0 && (
              <>
                {' '}
                Omitidos del selector: {(config.workers_invalid ?? []).join(', ')}.
              </>
            )}
          </p>
        )}
        {activeProject && (
          <p className="mx-4 mb-2 text-xs text-gov-blue-800 dark:text-dark-cyan bg-gov-cyan-50 dark:bg-dark-bg border border-gov-cyan-200 dark:border-dark-border px-3 py-2 rounded-xl">
            Proyecto activo: <strong>{activeProject.name}</strong>. El selector de agentes queda limitado a
            `admin_project_agents` para este proyecto.
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

      {!panelOpen && (
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          className="hidden lg:flex fixed right-6 top-1/2 -translate-y-1/2 z-20 items-center gap-1 px-2 py-3 rounded-l-2xl bg-white dark:bg-dark-surface border border-r-0 dark:border-dark-border shadow-md text-xs font-bold text-gov-blue-700 hover:bg-gov-gray-50 dark:hover:bg-dark-bg"
          title="Mostrar panel lateral"
        >
          <PanelRightOpen size={18} />
        </button>
      )}

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
            <PanelToggleButton
              open={panelOpen}
              onToggle={() => setPanelOpen((o) => !o)}
              openLabel="Ocultar panel"
              closedLabel="Panel"
              openIcon={PanelRightClose}
              closedIcon={PanelRightOpen}
              title={panelOpen ? 'Ocultar panel de configuración' : 'Mostrar panel de configuración'}
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1 space-y-4">
            <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4 space-y-3">
              <h2 className="font-bold text-sm flex items-center gap-2">
                <Settings2 size={18} /> Run settings
              </h2>
              <p className="text-[10px] text-gov-gray-500">{config?.note}</p>
              <ConfigRowsSection config={config} activeCatalog={activeCatalog} />
            </section>
            <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4">
              <h3 className="font-bold text-xs uppercase text-gov-gray-500 mb-2">
                Bóveda DuckDB (conversación)
              </h3>
              {conv.sessionId ? (
                <ConversationVaultSelector
                  chatId={conv.sessionId}
                  tenantId={config?.effective_tenant_id}
                  value={chat.vaultPath}
                  effectivePath={config?.vault?.effective_path}
                  scope={config?.vault?.scope}
                  options={config?.vault_options}
                  onChange={chat.setVaultPath}
                  onUpdated={loadConfig}
                />
              ) : (
                <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
              )}
            </section>
            <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4">
              <h3 className="font-bold text-xs uppercase text-gov-gray-500 mb-2">
                Proveedores disponibles
              </h3>
              {conv.sessionId ? (
                <LlmProviderCatalog
                  chatId={conv.sessionId}
                  catalog={config?.catalog ?? []}
                  onUpdated={loadConfig}
                />
              ) : (
                <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
              )}
            </section>
            <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4">
              <h3 className="font-bold text-xs uppercase text-gov-gray-500 mb-2">
                Instrucciones del agente
              </h3>
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
            </section>
          </div>
        </div>
      </aside>
    </div>
  );
}

function ConfigRowsSection({
  config,
  activeCatalog,
}: {
  config: Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null;
  activeCatalog?: { hint: string };
}) {
  return (
    <>
      <div className="rounded-xl bg-gov-gray-50 dark:bg-dark-bg p-3 text-xs space-y-2">
        <Row label="Proveedor activo" value={config?.llm?.provider || '—'} highlight />
        <Row label="Modelo" value={config?.llm?.model || '—'} />
        <Row label="Base URL" value={config?.llm?.base_url || '—'} mono />
        {config?.llm?.scope === 'chat' && (
          <p className="text-[10px] text-gov-blue-700 dark:text-dark-cyan pt-1">
            Override por conversación (equivalente a /model).
          </p>
        )}
        <Row
          label="Bóveda activa"
          value={config?.vault?.effective_path || '—'}
          mono
          highlight={config?.vault?.scope === 'chat'}
        />
        {config?.vault?.scope === 'chat' && (
          <p className="text-[10px] text-gov-blue-700 dark:text-dark-cyan pt-1">
            DuckDB fijada para esta conversación (no por worker).
          </p>
        )}
        {activeCatalog && (
          <p className="text-[10px] text-gov-gray-500 pt-1">{activeCatalog.hint}</p>
        )}
      </div>
      <Link href="/settings" className="text-xs text-gov-blue-700 font-semibold block">
        Variables globales (.env) →
      </Link>
    </>
  );
}

function Row({
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
    <div>
      <p className="text-gov-gray-500">{label}</p>
      <p
        className={`${mono ? 'font-mono break-all' : ''} ${highlight ? 'font-bold text-gov-blue-800 dark:text-dark-cyan' : ''}`}
      >
        {value}
      </p>
    </div>
  );
}
