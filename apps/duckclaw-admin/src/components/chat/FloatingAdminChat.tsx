'use client';

import { useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Bot, X, Maximize2 } from 'lucide-react';
import { AdminChatPanel } from '@/components/chat/AdminChatPanel';
import { useAdminChat } from '@/components/chat/useAdminChat';
import { titleForAdminPath } from '@/config/adminNav';

function chatIdForPath(pathname: string): string {
  const slug = pathname.replace(/^\/+|\/+$/g, '').replace(/\//g, '-') || 'root';
  return `admin-section-${slug}`;
}

/** Si la ruta es /templates/[workerId], usar ese agente por defecto. */
function workerFromPath(pathname: string): string {
  const match = pathname.match(/^\/templates\/([^/]+)/);
  if (!match?.[1]) return '';
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export function FloatingAdminChat() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const chatId = useMemo(() => chatIdForPath(pathname), [pathname]);
  const sectionTitle = titleForAdminPath(pathname);
  const pathWorker = useMemo(() => workerFromPath(pathname), [pathname]);
  const chat = useAdminChat({ chatId, initialWorker: pathWorker });
  const { workerId, loading } = chat;

  const activeWorkerLabel = workerId || '…';

  if (pathname === '/playground' || pathname.startsWith('/playground/')) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2 pointer-events-none">
      {open && (
        <div
          className="pointer-events-auto w-[min(100vw-2rem,380px)] h-[min(72vh,560px)] flex flex-col animate-in slide-in-from-bottom-4 fade-in duration-200"
          role="dialog"
          aria-label={`Chat en ${sectionTitle}`}
        >
          <div className="flex items-center justify-between gap-2 px-1 pb-1 pointer-events-auto">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted truncate">
              {sectionTitle}
            </p>
            <div className="flex items-center gap-1">
              <Link
                href="/playground"
                className="p-1.5 rounded-lg text-gov-blue-700 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                title="Abrir Playground completo"
              >
                <Maximize2 size={16} />
              </Link>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                aria-label="Cerrar chat"
              >
                <X size={18} />
              </button>
            </div>
          </div>
          <AdminChatPanel
            chatId={chatId}
            chat={chat}
            variant="compact"
            emptyHint={`Pregunta sobre ${sectionTitle}…`}
            showWorkerLink={false}
            className="flex-1 min-h-0 pointer-events-auto"
          />
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="pointer-events-auto flex items-center gap-2 px-3 py-2.5 sm:px-4 sm:py-3 rounded-full bg-gov-blue-700 text-white font-bold text-sm shadow-lg hover:bg-gov-blue-800 transition-colors max-w-[min(100vw-2rem,280px)]"
        aria-expanded={open}
        aria-label={
          open
            ? 'Cerrar asistente'
            : `Abrir asistente, agente activo ${activeWorkerLabel}`
        }
      >
        {open ? (
          <>
            <X size={20} aria-hidden />
            <span>Cerrar</span>
          </>
        ) : (
          <>
            <Bot size={20} className="shrink-0" aria-hidden />
            <span className="flex flex-col items-start min-w-0 leading-tight text-left">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-white/80">
                Agente
              </span>
              <span className="truncate max-w-[180px] text-sm" title={activeWorkerLabel}>
                {loading ? '…' : activeWorkerLabel}
              </span>
            </span>
          </>
        )}
      </button>
    </div>
  );
}
