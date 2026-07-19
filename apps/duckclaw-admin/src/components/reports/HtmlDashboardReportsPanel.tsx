'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { adminService } from '@/services/adminService';

const UI_DESIGNER_WORKER = 'ui_designer';

export function HtmlDashboardReportsPanel() {
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [reportReloadToken, setReportReloadToken] = useState(0);
  const [reportLoadError, setReportLoadError] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [reportHasContent, setReportHasContent] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const conv = useActiveConversation(config?.effective_tenant_id, 'reports', {
    defaultWorkerId: UI_DESIGNER_WORKER,
  });
  const reportId = conv.sessionId ?? '';
  const onReportActivityRef = useRef<() => void>(() => {});

  const chat = useAdminChat({
    chatId: reportId,
    initialWorker: UI_DESIGNER_WORKER,
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
      if (!cancelled) setConfig(c);
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
          <h2 className="text-lg font-semibold">Diseñador HTML</h2>
          <p className="text-xs text-slate-400">
            Agente <code className="text-slate-300">ui_designer</code> — publica con{' '}
            <code className="text-slate-300">publish_custom_report</code>.
          </p>
        </div>
        <div className="min-h-0 flex-1">
          {reportId ? (
            <AdminChatPanel
              chatId={reportId}
              initialWorker={UI_DESIGNER_WORKER}
              chat={chat}
              variant="compact"
              sectionTitle="Reportes"
              showWorkerLink={false}
              emptyHint="Pide un gráfico o cambia colores del dashboard."
              className="h-full"
            />
          ) : (
            <div className="p-4 text-sm text-slate-500">Iniciando sesión de chat…</div>
          )}
        </div>
      </div>
    </div>
  );
}
