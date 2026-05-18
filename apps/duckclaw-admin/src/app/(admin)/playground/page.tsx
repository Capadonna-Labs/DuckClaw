'use client';

import { useCallback, useEffect, useState } from 'react';
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
import { LlmProviderCatalog } from '@/components/chat/LlmProviderCatalog';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';

export default function PlaygroundPage() {
  const searchParams = useSearchParams();
  const initialWorker = searchParams.get('worker') || '';
  const [panelOpen, setPanelOpen] = useState(true);
  const [systemPreview, setSystemPreview] = useState('');
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [workerId, setWorkerId] = useState(initialWorker);

  const conv = useActiveConversation(config?.effective_tenant_id, 'playground');
  const chat = useAdminChat({
    chatId: conv.sessionId ?? '',
    initialWorker: workerId,
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
          if (initialWorker && c.workers?.includes(initialWorker)) return initialWorker;
          if (c.workers?.includes('default')) return 'default';
          return c.workers?.[0] ?? '';
        });
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

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[calc(100vh-8rem)] relative">
      {conv.sessionId && (
        <ConversationInbox
          tenantId={config?.effective_tenant_id}
          defaultSectionFilter=""
          activeSessionId={conv.sessionId}
          refreshToken={conv.refreshToken}
          onSelect={(id, meta) => conv.selectConversation(id, meta?.title)}
          onTitleRenamed={(_id, title) => conv.syncConversationTitle(title)}
          className="hidden md:flex rounded-3xl border dark:border-dark-border overflow-hidden bg-white dark:bg-dark-surface"
        />
      )}

      <div className="flex-1 flex flex-col min-w-0 min-h-[calc(100vh-8rem)] bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
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
            <label className="text-xs font-bold text-gov-gray-500">Agente</label>
            <select
              value={workerId}
              onChange={(e) => setWorkerId(e.target.value)}
              className="text-sm px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg max-w-[200px]"
            >
              {(config?.workers ?? []).map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
            <Link
              href={`/templates/${workerId}`}
              className="text-xs text-gov-blue-700 font-semibold flex items-center gap-1"
            >
              Editar <ChevronRight size={12} />
            </Link>
          </div>
        </header>
        {conv.bootstrapping || !conv.sessionId ? (
          <p className="flex-1 flex items-center justify-center text-sm text-gov-gray-400 p-8">
            Cargando conversación…
          </p>
        ) : (
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
            className="flex-1 border-0 rounded-none shadow-none"
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
        className={`shrink-0 overflow-hidden transition-[width,opacity] duration-300 ease-out ${
          panelOpen
            ? 'w-full lg:w-80 opacity-100'
            : 'w-0 max-w-0 opacity-0 pointer-events-none lg:hidden'
        }`}
        aria-hidden={!panelOpen}
      >
        <div className="w-full lg:w-80 space-y-4">
          <div className="flex items-center justify-between gap-2 sticky top-0 z-10 py-1">
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
          <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4 space-y-3">
            <h2 className="font-bold text-sm flex items-center gap-2">
              <Settings2 size={18} /> Run settings
            </h2>
            <p className="text-[10px] text-gov-gray-500">{config?.note}</p>
            <ConfigRowsSection config={config} activeCatalog={activeCatalog} />
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
