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

function earliestStartedAt(messages: ChatMsg[]): number | null {
  let min: number | null = null;
  for (const m of messages) {
    const t = m.toolStartedAt;
    if (t == null) continue;
    min = min == null ? t : Math.min(min, t);
  }
  return min;
}

function GroupedToolRow({
  grouped,
  identityLabel,
}: {
  grouped: GroupedToolInvocation;
  identityLabel: string;
}) {
  const { toolName, count, maxMs, averageMs, isRunning, isError, messages } = grouped;
  const runningStartedAt = earliestRunningStartedAt(messages);
  const liveMs = useLiveToolElapsedMs(isRunning, runningStartedAt);
  const max = formatToolDurationMs(maxMs);
  const avg = formatToolDurationMs(averageMs);
  const live = formatToolDurationMs(liveMs);
  const identityPrefix = formatChatIdentityPrefix(identityLabel);

  let timing = '';
  if (isRunning && live) {
    timing = ` · ${live}`;
  } else if (count > 1 && max) {
    timing = ` · max: ${max}`;
  } else if (count === 1 && max) {
    timing = ` · ${max}`;
  } else if (isRunning) {
    timing = ' · en curso';
  }

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
        {timing ? (
          <span className="tabular-nums">{timing}</span>
        ) : null}
        {count > 1 && avg && !isRunning ? (
          <span className="text-sky-600/80 dark:text-sky-400/80 tabular-nums"> · avg: {avg}</span>
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
  /** @deprecated Ignored — live header only while a tool is actually running. */
  liveWhileLoading?: boolean;
}) {
  const panelId = useId();
  const items = indices.map((i) => messages[i]).filter(Boolean);
  const anyRunning = toolGroupHasRunning(messages, indices);
  const totalMs = toolGroupTotalElapsedMs(messages, indices);
  const [isOpen, setIsOpen] = useState(false);

  const blockStartedAt = earliestStartedAt(items);
  // Solo tick en vivo mientras hay tool running. Antes, liveWhileLoading + tools
  // ya cerrados usaba el startedAt más viejo → cabecera "30m" tras un
  // invoke_worker de ~3m si el turno seguía en loading.
  const headerRunning = anyRunning;
  const liveHeaderMs = useLiveToolElapsedMs(headerRunning, blockStartedAt);
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
            <span className="normal-case font-semibold text-sky-600 dark:text-sky-400 tabular-nums">
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
