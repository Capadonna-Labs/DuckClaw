'use client';

import { useCallback, useEffect, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ChatMsg } from '@/components/chat/types';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { formatChatIdentityPrefix } from '@/lib/workerOptions';
import { formatToolDurationMs, isToolHeartbeatRunning } from '@/lib/toolHeartbeat';
import {
  toolGroupCurrentToolName,
  toolGroupHasRunning,
  toolGroupTotalElapsedMs,
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

function newestFinishedAt(messages: ChatMsg[]): number | null {
  let newest: number | null = null;
  for (const m of messages) {
    if (isToolHeartbeatRunning(m)) continue;
    const start = m.toolStartedAt;
    if (start == null || !Number.isFinite(start)) continue;
    const elapsed = m.toolElapsedMs;
    const finishedAt =
      elapsed != null && Number.isFinite(elapsed) ? start + Math.max(0, elapsed) : start;
    newest = newest == null ? finishedAt : Math.max(newest, finishedAt);
  }
  return newest;
}

function formatFinishedTimestamp(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return '';
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(ms));
}

function GroupedToolRow({
  grouped,
  identityLabel,
}: {
  grouped: GroupedToolInvocation;
  identityLabel: string;
}) {
  const { toolName, count, latestMs, maxMs, averageMs, isRunning, isError, messages } = grouped;
  const runningStartedAt = earliestRunningStartedAt(messages);
  const liveMs = useLiveToolElapsedMs(isRunning, runningStartedAt);
  const max = formatToolDurationMs(maxMs);
  const avg = formatToolDurationMs(averageMs);
  const live = formatToolDurationMs(liveMs);
  const finishedDuration = formatToolDurationMs(latestMs);
  const finishedAt = formatFinishedTimestamp(isRunning ? null : newestFinishedAt(messages));
  const finishedLabel = [finishedDuration, finishedAt].filter(Boolean).join(' · ');
  // Prefer the row's own workerId (e.g. quant_analyst->quant-trader) over the
  // group-level label from the first tool.
  const rowWorker =
    (newestToolMessage(messages)?.workerId || '').trim() || identityLabel;
  const identityPrefix = formatChatIdentityPrefix(
    rowWorker.includes('->')
      ? rowWorker.split('->').pop()?.trim() || rowWorker
      : rowWorker
  );

  return (
    <li className="px-3 py-1.5 text-sm text-sky-950 dark:text-sky-100">
      <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
        {identityPrefix ? (
          <span className="text-sky-700/80 dark:text-sky-300/80">{identityPrefix} · </span>
        ) : null}
        {toolName}
        {count > 1 ? (
          <span className="font-semibold text-sky-700 dark:text-sky-300"> x{count}</span>
        ) : null}
        {isError ? ' · error' : ''}
        {max ? (
          <span className="tabular-nums"> · max: {max}</span>
        ) : null}
        {avg ? (
          <span className="text-sky-600/80 dark:text-sky-400/80 tabular-nums"> · avg: {avg}</span>
        ) : null}
        {isRunning && live ? (
          <span className="text-sky-600/80 dark:text-sky-400/80 tabular-nums animate-pulse">
            {' '}
            · now: {live}
          </span>
        ) : isRunning ? (
          <span className="text-sky-600/80 dark:text-sky-400/80"> · now: en curso</span>
        ) : finishedLabel ? (
          <span className="text-sky-600/80 dark:text-sky-400/80 tabular-nums">
            {' '}
            · finished: {finishedLabel}
          </span>
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
