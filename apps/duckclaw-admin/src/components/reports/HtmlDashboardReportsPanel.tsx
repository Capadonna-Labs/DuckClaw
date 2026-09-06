'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { adminService } from '@/services/adminService';
import { useActiveConversation } from '@/components/chat/useActiveConversation';
import { HtmlDashboardUploadZone } from '@/components/reports/HtmlDashboardUploadZone';
import { isHtmlReportIncomplete, isHtmlReportPlaceholder, titleFromHtmlContent, validateHtmlUploadText } from '@/lib/htmlDashboardUpload';
import { sectionFromPath } from '@/lib/conversationStorage';

type ReportViewMode = 'render' | 'code';

async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallback below */
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export function HtmlDashboardReportsPanel() {
  const pathname = usePathname();
  const section = useMemo(() => sectionFromPath(pathname || ''), [pathname]);
  const [tenantId, setTenantId] = useState<string | undefined>();
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [reportReloadToken, setReportReloadToken] = useState(0);
  const [reportLoadError, setReportLoadError] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [reportIsPlaceholder, setReportIsPlaceholder] = useState(true);
  const [reportHtmlSource, setReportHtmlSource] = useState('');
  const [savedHtmlSource, setSavedHtmlSource] = useState('');
  const [viewMode, setViewMode] = useState<ReportViewMode>('render');
  const [copied, setCopied] = useState(false);
  const [uploadPending, setUploadPending] = useState(false);
  const [savePending, setSavePending] = useState(false);
  const [editorError, setEditorError] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const copyResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const conv = useActiveConversation(tenantId, section, {
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
      const incomplete = isHtmlReportIncomplete(text);
      setReportIsPlaceholder(placeholder);
      setReportHtmlSource(text);
      setSavedHtmlSource(text);
      setEditorError('');
      if (incomplete) {
        const low = text.toLowerCase();
        setReportLoadError(
          `Dashboard HTML incompleto en DB (${text.length} bytes, </html>=${low.includes('</html>')}, <body>=${low.includes('<body')}). ` +
            'Pide al asistente usar inspect_custom_report y republicar con publish_custom_report.'
        );
      } else if (!placeholder) {
        setReportLoadError('');
      }
      return placeholder || incomplete;
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
    const chatId = (reportId || '').trim();
    adminService
      .getPlaygroundConfig(chatId ? { chat_id: chatId, tenant_id: tenantId } : tenantId ? { tenant_id: tenantId } : undefined)
      .then((c) => {
        if (!cancelled) {
          setConfig(c);
          setTenantId(c.effective_tenant_id);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reportId, tenantId, section]);

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
          if (viewMode === 'render' || reportHtmlSource === savedHtmlSource) {
            void verifyReportReachable();
          }
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
  }, [reportId, reloadReportIframe, verifyReportReachable, viewMode, reportHtmlSource, savedHtmlSource]);

  const publishHtmlSource = useCallback(
    async (html: string) => {
      if (!reportId || !vaultPath) return false;
      const validationError = validateHtmlUploadText(html);
      if (validationError) {
        setEditorError(validationError);
        return false;
      }
      setSavePending(true);
      setEditorError('');
      setReportLoadError('');
      try {
        const file = new File([html], 'dashboard.html', { type: 'text/html;charset=utf-8' });
        await adminService.uploadCustomReportHtml(reportId, {
          vault: vaultPath,
          file,
          title: titleFromHtmlContent(html),
        });
        setSavedHtmlSource(html);
        reloadReportIframe();
        const deadline = Date.now() + 20_000;
        while (Date.now() < deadline) {
          const stillPlaceholder = await verifyReportReachable();
          if (!stillPlaceholder) break;
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
        return true;
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Error publicando HTML';
        setEditorError(msg);
        return false;
      } finally {
        setSavePending(false);
      }
    },
    [reportId, vaultPath, reloadReportIframe, verifyReportReachable]
  );

  const handleSaveSource = useCallback(async () => {
    const ok = await publishHtmlSource(reportHtmlSource);
    if (ok) setViewMode('render');
  }, [publishHtmlSource, reportHtmlSource]);

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
  const showViewToggle = reportReady && !showUploadZone && Boolean(reportHtmlSource.trim());
  const htmlDirty = reportHtmlSource !== savedHtmlSource;

  const handleCopySource = useCallback(async () => {
    if (!reportHtmlSource.trim()) return;
    const ok = await copyTextToClipboard(reportHtmlSource);
    if (!ok) return;
    setCopied(true);
    if (copyResetTimerRef.current) clearTimeout(copyResetTimerRef.current);
    copyResetTimerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [reportHtmlSource]);

  useEffect(
    () => () => {
      if (copyResetTimerRef.current) clearTimeout(copyResetTimerRef.current);
    },
    []
  );

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
            <div
              role="alert"
              className="absolute inset-x-0 top-0 z-40 max-h-[40vh] overflow-y-auto border-b-2 border-red-400 bg-white px-4 py-3 text-sm font-semibold leading-relaxed text-black shadow-lg"
            >
              <p className="mb-1 text-xs font-bold uppercase tracking-wide text-red-700">
                Error del lienzo HTML
              </p>
              <p className="whitespace-pre-wrap text-black">{reportLoadError}</p>
            </div>
          ) : null}
          {showUploadZone ? (
            <HtmlDashboardUploadZone disabled={uploadPending} onUpload={handleUpload} />
          ) : null}
          {showViewToggle && viewMode === 'render' ? (
            <div className="absolute right-3 top-3 z-50 flex rounded-lg border border-slate-600/80 bg-slate-900/90 p-0.5 shadow-lg backdrop-blur-sm">
              <button
                type="button"
                onClick={() => setViewMode('render')}
                className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-medium text-white"
              >
                Vista
              </button>
              <button
                type="button"
                onClick={() => setViewMode('code')}
                className="rounded-md px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:text-white"
              >
                Código
              </button>
            </div>
          ) : null}
          {viewMode === 'render' ? (
            <iframe
              ref={iframeRef}
              key={reportIframeSrc}
              src={reportIframeSrc || undefined}
              className="h-full w-full bg-white"
              title="Custom Report Viewer"
              sandbox="allow-scripts allow-same-origin"
              onLoad={() => setReportLoading(false)}
            />
          ) : (
            <div className="flex h-full flex-col bg-slate-950">
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-900 px-3 py-2">
                <div className="flex rounded-lg border border-slate-600/80 bg-slate-950 p-0.5">
                  <button
                    type="button"
                    onClick={() => setViewMode('render')}
                    className="rounded-md px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:text-white"
                  >
                    Vista
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('code')}
                    className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-medium text-white"
                  >
                    Código
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                  <span className="text-xs font-medium text-slate-400">
                    HTML fuente · {reportHtmlSource.length.toLocaleString()} caracteres
                    {htmlDirty ? ' · sin guardar' : ''}
                  </span>
                  <button
                    type="button"
                    onClick={() => void handleCopySource()}
                    disabled={!reportHtmlSource.trim()}
                    className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-100 transition hover:bg-slate-700 disabled:opacity-50"
                  >
                    {copied ? 'Copiado' : 'Copiar'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleSaveSource()}
                    disabled={!htmlDirty || savePending || !reportHtmlSource.trim()}
                    className="rounded-md border border-emerald-700 bg-emerald-800 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {savePending ? 'Guardando…' : 'Guardar'}
                  </button>
                </div>
              </div>
              {editorError ? (
                <p role="alert" className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-3 py-2 text-xs text-red-200">
                  {editorError}
                </p>
              ) : null}
              <textarea
                value={reportHtmlSource}
                onChange={(e) => {
                  setReportHtmlSource(e.target.value);
                  if (editorError) setEditorError('');
                }}
                spellCheck={false}
                aria-label="Editor HTML del dashboard"
                className="min-h-0 flex-1 resize-none border-0 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-200 outline-none focus:ring-0"
              />
            </div>
          )}
        </div>
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-slate-400">
          Cargando vault y conversación…
        </div>
      )}
    </div>
  );
}
