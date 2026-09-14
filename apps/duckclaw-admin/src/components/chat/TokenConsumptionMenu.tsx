'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  formatTokenCount,
  formatUsageTokensLogLine,
  type UsageTokenBreakdown,
} from '@/lib/formatTokenCount';
import type { ContextTokenBreakdown } from '@/lib/contextTokenBreakdown';
import { formatCompactTokenCount, inferModelContextWindow } from '@/lib/modelContextWindow';

export type TokenConsumptionMenuProps = {
  tokenUsage?: UsageTokenBreakdown | null;
  contextEstimatedTokens?: number | null;
  contextTokenBreakdown?: ContextTokenBreakdown | null;
  model?: string | null;
  className?: string;
};

function clampPct(n: number): number {
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.min(100, Math.max(0, n));
}

function SegmentBar({
  segments,
}: {
  segments: Array<{ pct: number; className: string; title?: string }>;
}) {
  const visible = segments.filter((s) => s.pct > 0);
  return (
    <div
      className="flex h-1.5 w-full overflow-hidden rounded-full bg-gov-gray-100 dark:bg-dark-bg"
      role="presentation"
    >
      {visible.map((seg, i) => (
        <div
          key={`${seg.className}-${i}`}
          className={`h-full ${seg.className}`}
          style={{ width: `${clampPct(seg.pct)}%` }}
          title={seg.title}
        />
      ))}
    </div>
  );
}

type CategoryRow = {
  key: string;
  label: string;
  tokens: number;
  className: string;
  muted?: boolean;
};

/** Botón + popover de consumo (estilo Claude): categorías de contexto + último turno. */
export function TokenConsumptionMenu({
  tokenUsage = null,
  contextEstimatedTokens = null,
  contextTokenBreakdown = null,
  model = null,
  className = '',
}: TokenConsumptionMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const contextWindow = useMemo(() => inferModelContextWindow(model), [model]);
  const contextUsed = useMemo(() => {
    if (contextTokenBreakdown && contextTokenBreakdown.total > 0) {
      return contextTokenBreakdown.total;
    }
    if (contextEstimatedTokens != null && contextEstimatedTokens > 0) {
      return Math.floor(contextEstimatedTokens);
    }
    if (tokenUsage && tokenUsage.input_tokens > 0) return tokenUsage.input_tokens;
    return null;
  }, [contextEstimatedTokens, contextTokenBreakdown, tokenUsage]);

  const contextPct =
    contextWindow && contextUsed != null
      ? clampPct((contextUsed / contextWindow) * 100)
      : null;

  const categoryRows = useMemo((): CategoryRow[] => {
    if (!contextWindow || contextUsed == null) return [];
    const bd = contextTokenBreakdown;
    const messages = bd?.messages ?? 0;
    const tools = bd?.tools ?? 0;
    const system = bd?.system ?? 0;
    const accounted = messages + tools + system;
    // When we only have a total (no breakdown), show a single "used" bucket.
    if (!bd || accounted <= 0) {
      const free = Math.max(0, contextWindow - contextUsed);
      return [
        { key: 'used', label: 'Usado', tokens: contextUsed, className: 'bg-gov-blue-500' },
        {
          key: 'free',
          label: 'Espacio libre',
          tokens: free,
          className: 'bg-gov-gray-300 dark:bg-dark-border',
          muted: true,
        },
      ];
    }
    const free = Math.max(0, contextWindow - accounted);
    return [
      { key: 'messages', label: 'Mensajes', tokens: messages, className: 'bg-gov-blue-500' },
      { key: 'tools', label: 'Herramientas', tokens: tools, className: 'bg-rose-500' },
      { key: 'system', label: 'System prompt', tokens: system, className: 'bg-amber-500' },
      {
        key: 'free',
        label: 'Espacio libre',
        tokens: free,
        className: 'bg-gov-gray-300 dark:bg-dark-border',
        muted: true,
      },
    ].filter((row) => row.tokens > 0 || row.key === 'free');
  }, [contextTokenBreakdown, contextUsed, contextWindow]);

  const contextSegments = useMemo(() => {
    if (!contextWindow || categoryRows.length === 0) {
      return [
        {
          pct: contextPct ?? (contextUsed != null ? 12 : 0),
          className: 'bg-gov-blue-500',
          title: 'Contexto usado',
        },
      ];
    }
    return categoryRows
      .filter((row) => row.key !== 'free')
      .map((row) => ({
        pct: (row.tokens / contextWindow) * 100,
        className: row.className,
        title: `${row.label} ${row.tokens.toLocaleString('es-CO')}`,
      }));
  }, [categoryRows, contextPct, contextUsed, contextWindow]);

  const turnTotal = tokenUsage?.total_tokens ?? 0;
  const turnPrompt = tokenUsage?.input_tokens ?? 0;
  const turnCompletion = tokenUsage?.output_tokens ?? 0;
  const promptShare = turnTotal > 0 ? (turnPrompt / turnTotal) * 100 : 0;
  const completionShare = turnTotal > 0 ? (turnCompletion / turnTotal) * 100 : 0;

  const buttonLabel =
    contextPct != null
      ? `${Math.round(contextPct)}%`
      : contextUsed != null
        ? formatCompactTokenCount(contextUsed)
        : turnTotal > 0
          ? formatCompactTokenCount(turnTotal)
          : '—';

  const hasData = Boolean(tokenUsage || (contextUsed != null && contextUsed > 0));
  const modelLabel = (model || '').trim();

  return (
    <div ref={rootRef} className={`relative shrink-0 ${className}`.trim()}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex max-w-[5.5rem] items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-medium tabular-nums transition-colors ${
          open
            ? 'border-gov-blue-300 bg-gov-blue-50 text-gov-blue-800 dark:border-gov-blue-800 dark:bg-gov-blue-950/40 dark:text-gov-blue-200'
            : 'border-gov-gray-200 bg-white/80 text-gov-gray-600 hover:bg-gov-gray-50 dark:border-dark-border dark:bg-dark-surface/80 dark:text-dark-muted dark:hover:bg-dark-bg'
        }`}
        aria-label="Consumo de tokens"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        title={
          tokenUsage
            ? formatUsageTokensLogLine(tokenUsage)
            : contextUsed != null
              ? `${formatTokenCount(contextUsed)} (contexto est.)`
              : 'Consumo de tokens'
        }
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-gov-blue-500" aria-hidden />
        <span className="truncate">{buttonLabel}</span>
      </button>

      {open ? (
        <div
          id={panelId}
          role="dialog"
          aria-label="Detalle de consumo"
          className="absolute right-0 top-full z-[70] mt-2 w-[18.5rem] max-w-[calc(100vw-1.25rem)] origin-top-right rounded-2xl border border-gov-gray-200 bg-white p-3 shadow-xl dark:border-dark-border dark:bg-dark-surface"
        >
          <div className="space-y-3">
            <section className="space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-medium text-gov-gray-900 dark:text-dark-text">
                  Ventana de contexto
                </p>
                <p className="shrink-0 text-right text-[11px] tabular-nums text-gov-gray-500 dark:text-dark-muted">
                  {contextUsed != null && contextWindow
                    ? `${formatCompactTokenCount(contextUsed)} / ${formatCompactTokenCount(contextWindow)} (${Math.round(contextPct ?? 0)}%)`
                    : contextUsed != null
                      ? `${formatCompactTokenCount(contextUsed)} (est.)`
                      : 'Sin estimado'}
                </p>
              </div>
              <SegmentBar segments={contextSegments} />
              {categoryRows.length > 0 ? (
                <dl className="mt-1.5 grid grid-cols-[1fr_auto_auto] gap-x-2 gap-y-1 text-[11px] tabular-nums">
                  {categoryRows.map((row) => {
                    const pct =
                      contextWindow && contextWindow > 0
                        ? (row.tokens / contextWindow) * 100
                        : 0;
                    return (
                      <div key={row.key} className="contents">
                        <dt
                          className={`flex items-center gap-1.5 ${
                            row.muted
                              ? 'text-gov-gray-400 dark:text-dark-muted'
                              : 'text-gov-gray-600 dark:text-dark-muted'
                          }`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-sm ${row.className}`} aria-hidden />
                          {row.label}
                        </dt>
                        <dd
                          className={
                            row.muted
                              ? 'text-gov-gray-400 dark:text-dark-muted'
                              : 'text-gov-gray-900 dark:text-dark-text'
                          }
                        >
                          {formatCompactTokenCount(row.tokens)}
                        </dd>
                        <dd className="text-right text-gov-gray-400 dark:text-dark-muted">
                          {pct.toFixed(1)}%
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              ) : null}
              {modelLabel ? (
                <p
                  className="truncate text-[10px] text-gov-gray-500 dark:text-dark-muted"
                  title={modelLabel}
                >
                  Modelo: {modelLabel}
                  {contextWindow ? '' : ' · límite desconocido'}
                </p>
              ) : null}
            </section>

            <div className="border-t border-gov-gray-100 dark:border-dark-border" />

            <section className="space-y-1.5">
              <p className="text-xs font-medium text-gov-gray-900 dark:text-dark-text">
                Último turno
              </p>
              {tokenUsage ? (
                <>
                  <SegmentBar
                    segments={[
                      {
                        pct: promptShare,
                        className: 'bg-gov-blue-500',
                        title: `Prompt ${turnPrompt.toLocaleString('es-CO')}`,
                      },
                      {
                        pct: completionShare,
                        className: 'bg-amber-500',
                        title: `Completion ${turnCompletion.toLocaleString('es-CO')}`,
                      },
                    ]}
                  />
                  <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[11px] tabular-nums">
                    <dt className="flex items-center gap-1.5 text-gov-gray-500 dark:text-dark-muted">
                      <span className="h-1.5 w-1.5 rounded-full bg-gov-blue-500" aria-hidden />
                      Prompt
                    </dt>
                    <dd className="text-gov-gray-900 dark:text-dark-text">
                      {turnPrompt.toLocaleString('es-CO')}
                    </dd>
                    <dt className="flex items-center gap-1.5 text-gov-gray-500 dark:text-dark-muted">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
                      Completion
                    </dt>
                    <dd className="text-gov-gray-900 dark:text-dark-text">
                      {turnCompletion.toLocaleString('es-CO')}
                    </dd>
                    <dt className="font-medium text-gov-gray-700 dark:text-dark-muted">Total</dt>
                    <dd className="font-medium text-gov-gray-900 dark:text-dark-text">
                      {turnTotal.toLocaleString('es-CO')}
                    </dd>
                  </dl>
                </>
              ) : (
                <p className="text-[11px] text-gov-gray-500 dark:text-dark-muted">
                  {hasData
                    ? 'Aún no hay desglose P/C del último turno.'
                    : 'Envía un mensaje para ver el consumo.'}
                </p>
              )}
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
