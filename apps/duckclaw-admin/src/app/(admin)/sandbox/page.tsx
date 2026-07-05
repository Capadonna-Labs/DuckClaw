'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Box, FolderOpen, Monitor, RefreshCw, Settings2 } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import { SandboxArtifactsExplorer } from '@/components/sandbox/SandboxArtifactsExplorer';
import { SandboxBrowserPanel } from '@/components/sandbox/SandboxBrowserPanel';
import { SandboxConfigPanel } from '@/components/sandbox/SandboxConfigPanel';
import { adminService } from '@/services/adminService';
import { cn } from '@/lib/utils';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';

type SandboxTab = 'files' | 'config' | 'browser';

const TABS: { id: SandboxTab; label: string; icon: typeof Box }[] = [
  { id: 'files', label: 'Archivos', icon: FolderOpen },
  { id: 'config', label: 'Configuración', icon: Settings2 },
  { id: 'browser', label: 'Navegador', icon: Monitor },
];

const STATUS_POLL_MS = 60_000;

export default function SandboxPage() {
  const searchParams = useSearchParams();
  const tabParam = (searchParams.get('tab') || 'files') as SandboxTab;
  const chatFromUrl = searchParams.get('chat') || '';
  const runFromUrl = searchParams.get('run') || '';

  const [tab, setTab] = useState<SandboxTab>(
    TABS.some((t) => t.id === tabParam) ? tabParam : 'files'
  );
  const [refreshKey, setRefreshKey] = useState(0);
  const [status, setStatus] = useState<Awaited<ReturnType<typeof adminService.getSandboxStatus>> | null>(
    null
  );
  const [policyChatId, setPolicyChatId] = useState('admin-sandbox-workspace');

  useEffect(() => {
    if (TABS.some((t) => t.id === tabParam)) setTab(tabParam);
  }, [tabParam]);

  useEffect(() => {
    if (tab !== 'config' && tab !== 'browser') return;
    adminService
      .getPlaygroundConfig()
      .then((cfg) => {
        setPolicyChatId((prev) => prev || cfg.team_chat_id || 'admin-sandbox-workspace');
      })
      .catch(() => undefined);
  }, [tab]);

  const loadStatus = useCallback(async () => {
    try {
      const st = await adminService.getSandboxStatus();
      setStatus(st);
    } catch {
      setStatus((prev) => prev);
    }
  }, []);

  const statusPollingEnabled = tab === 'files' || tab === 'config';

  useEffect(() => {
    if (!statusPollingEnabled) return;
    void loadStatus();
  }, [loadStatus, statusPollingEnabled, refreshKey]);

  useVisibilityAwareInterval(
    () => {
      if (statusPollingEnabled) void loadStatus();
    },
    statusPollingEnabled ? STATUS_POLL_MS : null
  );

  const dockerOk = status?.docker_available === true;

  const headerBadge = useMemo(() => {
    if (!status) return null;
    if (status.ready) {
      return (
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
          Docker OK
        </span>
      );
    }
    return (
      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        Revisar host
      </span>
    );
  }, [status]);

  return (
    <PageShell>
      <header className="flex flex-wrap items-end justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-black dark:text-dark-text flex items-center gap-2">
            <Box size={26} />
            Sandbox
            {headerBadge}
          </h1>
          <p className="text-sm text-gov-gray-500 mt-1 max-w-2xl">
            Código y archivos que el agente crea al ejecutar tareas. Actívalo en Chat con{' '}
            <code className="font-mono text-xs">/sandbox on</code>. Los resultados aparecen aquí en vivo.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void loadStatus();
            setRefreshKey((k) => k + 1);
          }}
          className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border flex items-center gap-2"
        >
          <RefreshCw size={16} />
          Actualizar
        </button>
      </header>

      {!dockerOk && status ? (
        <div className="rounded-xl border border-amber-300/60 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm text-amber-900 dark:text-amber-100">
          <p className="font-semibold">Docker no disponible en el gateway</p>
          <ul className="mt-1 list-disc pl-5 text-xs space-y-0.5">
            {(status.hints ?? []).map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div
        className="flex shrink-0 gap-1 border-b border-gov-gray-200 dark:border-dark-border"
        role="tablist"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors',
              tab === id
                ? 'border-gov-blue-600 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                : 'border-transparent text-gov-gray-500 hover:text-gov-gray-800 dark:hover:text-dark-text'
            )}
          >
            <Icon size={16} aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1 flex-col pt-4">
        {tab === 'files' ? (
          <div className="min-h-[min(70vh,720px)] flex-1">
            <SandboxArtifactsExplorer
              chatId={chatFromUrl}
              highlightRunId={runFromUrl}
              refreshKey={refreshKey}
            />
          </div>
        ) : null}

        {tab === 'config' ? (
          <SandboxConfigPanel
            defaultChatId={policyChatId}
            onChatIdChange={setPolicyChatId}
            status={status}
            onRefresh={() => {
              void loadStatus();
              setRefreshKey((k) => k + 1);
            }}
          />
        ) : null}

        {tab === 'browser' ? (
          <SandboxBrowserPanel defaultChatId={policyChatId} status={status} />
        ) : null}
      </div>
    </PageShell>
  );
}
