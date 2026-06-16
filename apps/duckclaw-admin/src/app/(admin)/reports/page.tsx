'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { adminService } from '@/services/adminService';

const UI_DESIGNER_WORKER = 'ui_designer';

export default function CustomReportsPage() {
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
      // region agent log
      fetch('http://127.0.0.1:7296/ingest/ba590886-0cb5-4d33-aba0-97f6faa90e06', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '97f3cb' },
        body: JSON.stringify({
          sessionId: '97f3cb',
          hypothesisId: 'H11',
          location: 'reports/page.tsx:verifyReportReachable',
          message: 'report_fetch_ok',
          data: {
            reportId,
            vaultTail: vaultPath.slice(-80),
            htmlLen: text.length,
            status: res.status,
            renderMode: 'iframe_src',
          },
          timestamp: Date.now(),
          runId: 'post-fix-4',
        }),
      }).catch(() => undefined);
      // endregion
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error cargando reporte';
      setReportLoadError(msg);
      setReportHasContent(false);
      // region agent log
      fetch('http://127.0.0.1:7296/ingest/ba590886-0cb5-4d33-aba0-97f6faa90e06', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '97f3cb' },
        body: JSON.stringify({
          sessionId: '97f3cb',
          hypothesisId: 'H11',
          location: 'reports/page.tsx:verifyReportReachable',
          message: 'report_fetch_fail',
          data: { reportId, err: msg.slice(0, 120) },
          timestamp: Date.now(),
          runId: 'post-fix-4',
        }),
      }).catch(() => undefined);
      // endregion
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
        // region agent log
        fetch('http://127.0.0.1:7296/ingest/ba590886-0cb5-4d33-aba0-97f6faa90e06', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '97f3cb' },
          body: JSON.stringify({
            sessionId: '97f3cb',
            hypothesisId: 'H8',
            location: 'reports/page.tsx:sse',
            message: 'sse_event',
            data: { reportId, data: event.data },
            timestamp: Date.now(),
            runId: 'post-fix-4',
          }),
        }).catch(() => undefined);
        // endregion
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
    <div className="flex h-[calc(100vh-4rem)] w-full overflow-hidden bg-slate-950 text-slate-100">
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
          <h2 className="text-lg font-semibold">Diseñador de Reportes</h2>
          <p className="text-xs text-slate-400">
            Agentes <code className="text-slate-300">ui_designer</code> o{' '}
            <code className="text-slate-300">ui-designer</code> — publican HTML con{' '}
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
