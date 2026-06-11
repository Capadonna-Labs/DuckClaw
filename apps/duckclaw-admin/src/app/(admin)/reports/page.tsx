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
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const conv = useActiveConversation(config?.effective_tenant_id, 'reports');
  const reportId = conv.sessionId ?? '';
  const vaultPath = config?.vault?.effective_path ?? '';

  const chat = useAdminChat({
    chatId: reportId,
    initialWorker: UI_DESIGNER_WORKER,
    enabled: Boolean(reportId),
    onConversationActivity: conv.bumpRefresh,
  });

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

  const reportSrc = useMemo(() => {
    if (!reportId || !vaultPath) return '';
    return `/api/admin/reports/${encodeURIComponent(reportId)}?vault=${encodeURIComponent(vaultPath)}`;
  }, [reportId, vaultPath]);

  const reloadIframe = useCallback(() => {
    const win = iframeRef.current?.contentWindow;
    if (win) {
      win.location.reload();
    }
  }, []);

  useEffect(() => {
    if (!reportId) return undefined;
    const es = new EventSource(`/api/admin/reports/${encodeURIComponent(reportId)}/stream`);
    es.onmessage = (event) => {
      if (event.data === 'reload') reloadIframe();
    };
    return () => es.close();
  }, [reportId, reloadIframe]);

  return (
    <div className="flex h-[calc(100vh-4rem)] w-full overflow-hidden bg-slate-950 text-slate-100">
      <div className="h-full w-[70%] border-r border-slate-800 bg-slate-900">
        {reportSrc ? (
          <iframe
            ref={iframeRef}
            src={reportSrc}
            className="h-full w-full bg-white"
            title="Custom Report Viewer"
            sandbox="allow-scripts allow-same-origin"
          />
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
            Agente <code className="text-slate-300">ui_designer</code> — edita el HTML en tiempo real.
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
