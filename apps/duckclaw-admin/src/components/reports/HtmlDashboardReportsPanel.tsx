'use client';

import Link from 'next/link';
import { Maximize2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { adminService } from '@/services/adminService';

export function HtmlDashboardReportsPanel() {
  const [tenantId, setTenantId] = useState<string | undefined>();
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [reportReloadToken, setReportReloadToken] = useState(0);
  const [reportLoadError, setReportLoadError] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [reportHasContent, setReportHasContent] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const conv = useActiveConversation(tenantId, 'reports', {
    defaultWorkerId: '',
  });
  const { createConversation, selectConversation } = conv;
  const reportId = conv.sessionId ?? '';
  const onReportActivityRef = useRef<() => void>(() => {});

  const chat = useAdminChat({
    chatId: reportId,
    initialWorker: '',
    enabled: Boolean(reportId),
    onConversationActivity: () => {
      conv.bumpRefresh();
      onReportActivityRef.current();
    },
    onConversationNotFound: conv.recoverMissingConversation,
  });
  const { vaultPath: chatVaultPath } = chat;

  const vaultPath =
    (chatVaultPath || '').trim() ||
    (config?.vault?.effective_path || '').trim();

  const reportIframeSrc = useMemo(() => {
    if (!reportId || !vaultPath) return '';
    const url = `/api/admin/reports/${encodeURIComponent(reportId)}?vault=${encodeURIComponent(
      vaultPath.trim()
    )}&_t=${reportReloadToken || Date.now()}`;
    return url;
  }, [reportId, vaultPath, reportReloadToken]);

  const reloadReportIframe = useCallback(() => {
    setReportLoadError('');
    setReportLoading(true);
    setReportHasContent(false);
    setReportReloadToken(Date.now());
  }, []);

  const verifyReportReachable = useCallback(async () => {
    if (!reportId || !vaultPath) return;
    const url = `/api/admin/reports/${encodeURIComponent(reportId)}?vault=${encodeURIComponent(
      vaultPath.trim()
    )}&_t=${Date.now()}`;
    setReportLoading(true);
    setReportLoadError('');
    try {
      const res = await fetch(url, { credentials: 'include', cache: 'no-store' });
      const text = await res.text();
      if (!res.ok) {
        throw new Error(text.slice(0, 200) || `HTTP ${res.status}`);
      }
      setReportHasContent(text.length > 0);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error cargando reporte';
      setReportLoadError(msg);
      setReportHasContent(false);
    } finally {
      setReportLoading(false);
    }
  }, [reportId, vaultPath]);

  useEffect(() => {
    onReportActivityRef.current = () => {
      reloadReportIframe();
      void verifyReportReachable();
    };
  }, [reloadReportIframe, verifyReportReachable]);

  useEffect(() => {
    let cancelled = false;
    adminService.getPlaygroundConfig().then((c) => {
      if (!cancelled) {
        setConfig(c);
        setTenantId(c.effective_tenant_id);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!conv.sessionId && config && !conv.bootstrapping) {
      void conv.createConversation();
    }
  }, [conv, config]);

  const reportReady = Boolean(reportId && vaultPath);

  useEffect(() => {
    if (!reportReady) return;
    reloadReportIframe();
    void verifyReportReachable();
  }, [reportReady, reloadReportIframe, verifyReportReachable]);

  useEffect(() => {
    if (!reportId) return undefined;
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let delayMs = 1000;

    const connect = () => {
      es?.close();
      es = new EventSource(`/api/admin/reports/${encodeURIComponent(reportId)}/stream`);
      es.onmessage = (event) => {
        delayMs = 1000;
        if (event.data === 'reload') {
          reloadReportIframe();
          void verifyReportReachable();
        }
      };
      es.onerror = () => {
        es?.close();
        reconnectTimer = setTimeout(() => {
          delayMs = Math.min(delayMs * 2, 15000);
          connect();
        }, delayMs);
      };
    };

    connect();
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      es?.close();
    };
  }, [reportId, reloadReportIframe, verifyReportReachable]);

  const headerActions = (
    <div className="flex items-center justify-end gap-1 shrink-0">
      <Link
        href="/playground"
        className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        title="Abrir Playground completo"
        aria-label="Abrir Playground completo"
      >
        <Maximize2 size={16} />
      </Link>
    </div>
  );

  return (
    <div className="flex h-full w-full overflow-hidden">
      <div className="h-full w-[70%] border-r border-slate-800 bg-slate-900">
        {reportReady ? (
          <div className="relative h-full w-full">
            {reportLoading && !reportHasContent ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/60 text-sm text-slate-300">
                Cargando reporte…
              </div>
            ) : null}
            {reportLoadError ? (
              <div className="absolute inset-x-0 top-0 z-20 border-b border-amber-700/50 bg-amber-950/80 px-4 py-2 text-xs text-amber-200">
                No se pudo cargar el lienzo: {reportLoadError}
              </div>
            ) : null}
            <iframe
              ref={iframeRef}
              key={reportIframeSrc}
              src={reportIframeSrc || undefined}
              className="h-full w-full bg-white"
              title="Custom Report Viewer"
              sandbox="allow-scripts allow-same-origin"
              onLoad={() => setReportLoading(false)}
            />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Cargando vault y conversación…
          </div>
        )}
      </div>
      <div className="flex h-full w-[30%] flex-col bg-slate-950">
        <div className="border-b border-slate-800 p-4">
          <h2 className="text-lg font-semibold">Asistente</h2>
          <p className="text-xs text-slate-400">
            Elige un agente y publica con{' '}
            <code className="text-slate-300">publish_custom_report</code> —{' '}
            <code className="text-slate-300">report_id</code> = id de esta conversación.
            Dashboards quant → agente <code className="text-slate-300">quant_reporter</code>.
          </p>
        </div>
        <div className="min-h-0 flex-1">
          {conv.bootstrapping || !reportId ? (
            <div className="p-4 text-sm text-slate-500">Iniciando sesión de chat…</div>
          ) : (
            <AdminChatPanel
              key={reportId}
              chatId={reportId}
              chat={chat}
              variant="compact"
              sectionTitle="Reportes"
              conversationTitle={conv.conversationTitle}
              showWorkerLink={false}
              headerActions={headerActions}
              onRenameConversation={conv.renameConversation}
              conversationManage={{
                tenantId,
                section: 'reports',
                refreshToken: conv.refreshToken,
                onSelect: (id, meta) => selectConversation(id, meta?.title),
                onCreateNew: () => void createConversation(),
              }}
              emptyHint="Pide un dashboard o cambia el diseño del reporte HTML."
              className="h-full"
            />
          )}
        </div>
      </div>
    </div>
  );
}
