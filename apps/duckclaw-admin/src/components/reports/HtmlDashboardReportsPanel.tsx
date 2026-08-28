'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { HtmlDashboardUploadZone } from '@/components/reports/HtmlDashboardUploadZone';
import { isHtmlReportPlaceholder } from '@/lib/htmlDashboardUpload';

export function HtmlDashboardReportsPanel() {
  const [tenantId, setTenantId] = useState<string | undefined>();
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [reportReloadToken, setReportReloadToken] = useState(0);
  const [reportLoadError, setReportLoadError] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [reportIsPlaceholder, setReportIsPlaceholder] = useState(true);
  const [uploadPending, setUploadPending] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const conv = useActiveConversation(tenantId, 'reports', {
    defaultWorkerId: '',
  });
  const reportId = conv.sessionId ?? '';

  const vaultPath = (config?.vault?.effective_path || '').trim();

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
    setReportReloadToken(Date.now());
  }, []);

  const verifyReportReachable = useCallback(async (): Promise<boolean> => {
    if (!reportId || !vaultPath) return true;
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
      const placeholder = isHtmlReportPlaceholder(text);
      setReportIsPlaceholder(placeholder);
      return placeholder;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error cargando reporte';
      setReportLoadError(msg);
      setReportIsPlaceholder(true);
      return true;
    } finally {
      setReportLoading(false);
    }
  }, [reportId, vaultPath]);

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

  const handleUpload = useCallback(
    async (file: File, title: string) => {
      if (!reportId || !vaultPath) return;
      setUploadPending(true);
      setReportLoadError('');
      try {
        await adminService.uploadCustomReportHtml(reportId, {
          vault: vaultPath,
          file,
          title,
        });
        reloadReportIframe();
        const deadline = Date.now() + 20_000;
        let stillPlaceholder = true;
        while (Date.now() < deadline && stillPlaceholder) {
          stillPlaceholder = await verifyReportReachable();
          if (stillPlaceholder) {
            await new Promise((resolve) => setTimeout(resolve, 500));
          }
        }
        if (stillPlaceholder) {
          setReportLoadError('Publicación encolada; recarga en unos segundos si no aparece.');
        }
      } finally {
        setUploadPending(false);
      }
    },
    [reportId, vaultPath, reloadReportIframe, verifyReportReachable]
  );

  const showUploadZone = reportReady && reportIsPlaceholder;

  return (
    <div className="h-full w-full overflow-hidden bg-slate-900">
      {reportReady ? (
        <div className="relative h-full w-full">
          {reportLoading && reportIsPlaceholder ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/60 text-sm text-slate-300">
              Cargando reporte…
            </div>
          ) : null}
          {reportLoadError ? (
            <div className="absolute inset-x-0 top-0 z-20 border-b border-amber-700/50 bg-amber-950/80 px-4 py-2 text-xs text-amber-200">
              No se pudo cargar el lienzo: {reportLoadError}
            </div>
          ) : null}
          {showUploadZone ? (
            <HtmlDashboardUploadZone disabled={uploadPending} onUpload={handleUpload} />
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
  );
}
