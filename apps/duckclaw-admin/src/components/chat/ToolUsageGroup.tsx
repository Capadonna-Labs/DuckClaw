'use client';

import { useCallback, useEffect, useId, useState } from 'react';
import { Check, ChevronDown, Loader2, X } from 'lucide-react';
import type { ChatMsg } from '@/components/chat/types';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { formatToolDurationMs, isToolHeartbeatRunning } from '@/lib/toolHeartbeat';
import {
  toolGroupCurrentToolName,
  toolGroupHasRunning,
  toolGroupTotalElapsedMs,
  toolRowDurationLabel,
  groupToolInvocationsByName,
  type GroupedToolInvocation,
} from '@/lib/toolUsageGroup';

/** Cronómetro en vivo mientras hay tools running (misma idea que ToolHeartbeatRow). */
function useLiveToolElapsedMs(running: boolean, startedAt: number | null | undefined): number | null {
  const [liveMs, setLiveMs] = useState<number | null>(null);
  const tick = useCallback(() => {
    if (!running || startedAt == null) {
      setLiveMs(null);
      return;
    }
    setLiveMs(Math.max(0, Date.now() - startedAt));
  }, [running, startedAt]);

  useEffect(() => {
    tick();
  }, [tick]);

  useVisibilityAwareInterval(tick, running && startedAt != null ? 50 : null);

  return running ? liveMs : null;
}

function earliestRunningStartedAt(messages: ChatMsg[]): number | null {
  let min: number | null = null;
  for (const m of messages) {
    if (!isToolHeartbeatRunning(m)) continue;
    const t = m.toolStartedAt;
    if (t == null) continue;
    min = min == null ? t : Math.min(min, t);
  }
  return min;
}

function newestToolMessage(messages: ChatMsg[]): ChatMsg | null {
  return messages.reduce<ChatMsg | null>((best, m) => {
    if (!best) return m;
    return (m.toolStartedAt ?? 0) >= (best.toolStartedAt ?? 0) ? m : best;
  }, null);
}

function GroupedToolRow({
  grouped,
  identityLabel,
}: {
  grouped: GroupedToolInvocation;
  identityLabel: string;
}) {
  const { toolName, count, isRunning, isError, messages } = grouped;
  const runningStartedAt = earliestRunningStartedAt(messages);
  const liveMs = useLiveToolElapsedMs(isRunning, runningStartedAt);
  const { primary, secondary } = toolRowDurationLabel(grouped, liveMs);
  // Worker (e.g. quant_analyst->quant-trader) moves to the tooltip; the swarm
  // slot number it used to print meant nothing to the reader.
  const rowWorker = (newestToolMessage(messages)?.workerId || '').trim() || identityLabel;
  const worker = rowWorker.split('->').pop()?.trim() || '';

  return (
    <li
      title={worker ? `Agente: ${worker}` : undefined}
      className="flex items-center gap-2 px-4 py-1.5 text-sm text-sky-950 dark:text-sky-100"
    >
      {isRunning ? (
        <Loader2 size={14} className="shrink-0 animate-spin text-sky-500" aria-label="En curso" />
      ) : isError ? (
        <X size={14} className="shrink-0 text-rose-500" aria-label="Error" />
      ) : (
        <Check size={14} className="shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Completado" />
      )}
      <span className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">{toolName}</span>
      {count > 1 ? (
        <span className="shrink-0 rounded-full bg-sky-100 px-1.5 text-[11px] font-semibold tabular-nums text-sky-700 dark:bg-sky-900/50 dark:text-sky-300">
          ×{count}
        </span>
      ) : null}
      <span className="shrink-0 text-right text-xs tabular-nums text-sky-700/90 dark:text-sky-300/90">
        <span className={isRunning ? 'animate-pulse' : undefined}>
          {primary || (isRunning ? 'en curso' : '')}
        </span>
        {secondary ? (
          <span className="block text-[10px] text-sky-600/70 dark:text-sky-400/70">{secondary}</span>
        ) : null}
      </span>
    </li>
  );
}

export function ToolUsageGroup({
  messages,
  indices,
  identityLabel = '',
  liveWhileLoading: _liveWhileLoading = false,
}: {
  messages: ChatMsg[];
  indices: number[];
  identityLabel?: string;
  /** @deprecated Ignored — the block is live only while a tool is actually running. */
  liveWhileLoading?: boolean;
}) {
  const panelId = useId();
  const items = indices.map((i) => messages[i]).filter(Boolean);
  const anyRunning = toolGroupHasRunning(messages, indices);
  const totalMs = toolGroupTotalElapsedMs(messages, indices);
  const [isOpen, setIsOpen] = useState(false);

  const runningStartedAt = earliestRunningStartedAt(items);
  const headerRunning = anyRunning && runningStartedAt != null;
  const liveHeaderMs = useLiveToolElapsedMs(headerRunning, runningStartedAt);
  const headerLiveTotal = headerRunning ? liveHeaderMs : null;
  void _liveWhileLoading;

  const count = items.length;
  const totalLabel =
    headerLiveTotal != null
      ? formatToolDurationMs(headerLiveTotal)
      : totalMs != null
        ? formatToolDurationMs(totalMs)
        : '';
  const currentTool = !isOpen ? toolGroupCurrentToolName(messages, indices) : '';

  const groupedInvocations = groupToolInvocationsByName(messages, indices);

  return (
    <div className="mx-auto w-full max-w-full min-w-0 rounded-2xl bg-sky-50 text-sky-950 border border-sky-200/80 dark:bg-sky-950/25 dark:text-sky-100 dark:border-sky-800/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
        aria-expanded={isOpen}
        aria-controls={panelId}
      >
        <span className="min-w-0 text-[10px] font-bold uppercase tracking-wider text-sky-700/90 dark:text-sky-300/90">
          Tool Usage ({count})
          {!isOpen && currentTool ? (
            <span className="normal-case font-semibold text-sky-600 dark:text-sky-400">
              {' '}
              · {currentTool}
            </span>
          ) : null}
          {totalLabel ? (
            <span
              className={`normal-case font-semibold text-sky-600 dark:text-sky-400 tabular-nums ${
                headerRunning ? 'animate-pulse' : ''
              }`}
            >
              {' '}
              · {totalLabel}
            </span>
          ) : headerRunning ? (
            <span className="normal-case font-semibold text-sky-600 dark:text-sky-400">
              {' '}
              · en curso
            </span>
          ) : null}
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-sky-600 dark:text-sky-400 transition-transform ${
            isOpen ? 'rotate-0' : '-rotate-90'
          }`}
          aria-hidden
        />
      </button>
      {isOpen ? (
        <ul id={panelId} role="list" className="border-t border-sky-200/80 dark:border-sky-800/60">
          {groupedInvocations.map((grouped, idx) => (
            <GroupedToolRow
              key={`${grouped.toolName}-${idx}`}
              grouped={grouped}
              identityLabel={identityLabel}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
