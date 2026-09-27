'use client';

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bot } from 'lucide-react';
import { formatGatewayStatus, isGatewayHealthy } from '@/lib/healthLabels';
import { workersTooltipLabel } from '@/lib/workersTooltipLabel';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

const POLL_OK_MS = 60_000;
const POLL_ERROR_MS = 30_000;

export function PlatformStatusStrip() {
  const recovering = useGatewayHealthStore((s) => s.recovering);
  const data = useGatewayHealthStore((s) => s.data);
  const error = useGatewayHealthStore((s) => s.error);
  const fetchedAt = useGatewayHealthStore((s) => s.fetchedAt);
  const refresh = useGatewayHealthStore((s) => s.refresh);

  const [workersOpen, setWorkersOpen] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null);
  const workersRootRef = useRef<HTMLSpanElement | null>(null);
  const workersButtonRef = useRef<HTMLButtonElement | null>(null);
  const workersPanelRef = useRef<HTMLSpanElement | null>(null);
  const workersPanelId = useId();

  const poll = useCallback(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  const intervalMs = useMemo(() => (error ? POLL_ERROR_MS : POLL_OK_MS), [error]);
  useVisibilityAwareInterval(poll, intervalMs);

  const workers = useMemo(
    () =>
      Array.isArray(data?.workers)
        ? data.workers.map((id) => String(id).trim()).filter(Boolean)
        : [],
    [data?.workers]
  );
  const workersCount =
    typeof data?.workers_count === 'number' ? data.workers_count : workers.length || null;

  const checking = !recovering && !error && data == null && fetchedAt === 0;
  const online = !recovering && !error && data != null && isGatewayHealthy(data.status);
  const gatewayLabel = recovering
    ? 'Recuperando…'
    : checking
      ? 'Comprobando…'
      : error
        ? 'Off-line'
        : formatGatewayStatus(data?.status);
  const workersTitle = useMemo(() => workersTooltipLabel(workers), [workers]);
  const gatewayTitle = recovering
    ? 'Recuperando stack…'
    : error
      ? 'Gateway no responde'
      : `Gateway ${gatewayLabel}`;

  const syncPanelPos = useCallback(() => {
    const btn = workersButtonRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    setPanelPos({
      top: rect.bottom + 8,
      left: rect.left + rect.width / 2,
    });
  }, []);

  useLayoutEffect(() => {
    if (!workersOpen) {
      setPanelPos(null);
      return;
    }
    syncPanelPos();
    const onReposition = () => syncPanelPos();
    window.addEventListener('resize', onReposition);
    window.addEventListener('scroll', onReposition, true);
    return () => {
      window.removeEventListener('resize', onReposition);
      window.removeEventListener('scroll', onReposition, true);
    };
  }, [workersOpen, syncPanelPos]);

  useEffect(() => {
    if (!workersOpen) return;
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (workersRootRef.current?.contains(target)) return;
      if (workersPanelRef.current?.contains(target)) return;
      setWorkersOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setWorkersOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [workersOpen]);

  const workersPanel =
    portalReady && workersOpen && panelPos
      ? createPortal(
          <span
            ref={workersPanelRef}
            id={workersPanelId}
            role="dialog"
            aria-label="Workers activos"
            style={{ top: panelPos.top, left: panelPos.left }}
            className="fixed z-[10050] w-max max-w-[min(18rem,calc(100vw-1.5rem))] -translate-x-1/2 rounded-lg border border-gov-gray-700 bg-gov-gray-900 px-3 py-2 text-left text-[11px] font-medium leading-snug text-white shadow-lg dark:border-dark-border dark:bg-[#1e1f20]"
          >
            {workers.length > 0 ? (
              <ul className="space-y-1">
                {workers.map((id) => (
                  <li key={id} className="whitespace-nowrap">
                    {id}
                  </li>
                ))}
              </ul>
            ) : (
              workersTitle
            )}
          </span>,
          document.body
        )
      : null;

  return (
    <div
      className="inline-flex min-h-[36px] items-stretch rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm overflow-visible shrink-0 dark:border-dark-border dark:bg-dark-bg/80"
      aria-label="Estado de la plataforma"
    >
      <span
        className={`inline-flex items-center ${recovering ? 'px-2' : 'gap-1.5 px-2.5'} py-2 ${
          recovering
            ? 'text-amber-800 dark:text-amber-300'
            : checking
              ? 'text-gov-gray-600 dark:text-dark-muted'
              : online
                ? 'text-emerald-800 dark:text-emerald-300'
                : 'text-red-800 dark:text-red-300'
        }`}
        title={gatewayTitle}
        aria-label={gatewayTitle}
      >
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full shrink-0 ${
            recovering
              ? 'bg-amber-500 animate-pulse'
              : checking
                ? 'bg-gov-gray-400 animate-pulse'
                : online
                  ? 'bg-emerald-500'
                  : 'bg-red-500'
          }`}
          aria-hidden
        />
        {!recovering ? <span className="text-xs font-bold">{gatewayLabel}</span> : null}
      </span>

      <span className="w-px self-stretch bg-gov-gray-200 dark:bg-dark-border" aria-hidden />

      <span ref={workersRootRef} className="relative inline-flex items-stretch">
        <button
          ref={workersButtonRef}
          type="button"
          onClick={() => setWorkersOpen((v) => !v)}
          className={`inline-flex items-center gap-1.5 px-2.5 py-2 text-gov-blue-800 dark:text-dark-cyan ${
            workersOpen ? 'bg-gov-blue-50 dark:bg-dark-surface' : 'hover:bg-gov-gray-50 dark:hover:bg-dark-surface/60'
          }`}
          title={workersTitle}
          aria-label={
            workers.length > 0 ? `Workers activos: ${workersCount}` : 'Sin workers activos'
          }
          aria-haspopup="dialog"
          aria-expanded={workersOpen}
          aria-controls={workersPanelId}
        >
          <Bot size={15} className="shrink-0 opacity-90" aria-hidden />
          <span className="text-xs font-black tabular-nums">{workersCount ?? '—'}</span>
        </button>
      </span>
      {workersPanel}
    </div>
  );
}

/** @deprecated Usa PlatformStatusStrip */
export function GatewayStatusBadge() {
  return <PlatformStatusStrip />;
}
