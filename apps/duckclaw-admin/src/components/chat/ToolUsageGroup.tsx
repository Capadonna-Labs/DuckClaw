'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ChatMsg } from '@/components/chat/types';
import { formatChatIdentityPrefix } from '@/lib/workerOptions';
import { formatToolDurationMs } from '@/lib/toolHeartbeat';
import {
  toolGroupCurrentToolName,
  toolGroupHasRunning,
  toolGroupTotalElapsedMs,
  groupToolInvocationsByName,
  type GroupedToolInvocation,
} from '@/lib/toolUsageGroup';

function GroupedToolRow({ 
  grouped, 
  identityLabel 
}: { 
  grouped: GroupedToolInvocation;
  identityLabel: string;
}) {
  const { toolName, count, latestMs, averageMs, isRunning, isError } = grouped;
  const latest = formatToolDurationMs(latestMs);
  const avg = formatToolDurationMs(averageMs);
  const identityPrefix = formatChatIdentityPrefix(identityLabel);

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
        {latest ? ` · last: ${latest}` : isRunning ? ' · en curso' : ''}
        {count > 1 && avg && !isRunning ? (
          <span className="text-sky-600/80 dark:text-sky-400/80"> · avg: {avg}</span>
        ) : null}
      </span>
    </li>
  );
}

export function ToolUsageGroup({
  messages,
  indices,
  identityLabel = '',
}: {
  messages: ChatMsg[];
  indices: number[];
  identityLabel?: string;
}) {
  const panelId = useId();
  const items = indices.map((i) => messages[i]).filter(Boolean);
  const anyRunning = toolGroupHasRunning(messages, indices);
  const totalMs = toolGroupTotalElapsedMs(messages, indices);
  const [isOpen, setIsOpen] = useState(false);

  const identityPrefix = formatChatIdentityPrefix(identityLabel);
  const count = items.length;
  const totalLabel = totalMs != null ? formatToolDurationMs(totalMs) : '';
  const currentTool = !isOpen ? toolGroupCurrentToolName(messages, indices) : '';

  // Agrupar herramientas repetidas
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
            <span className="normal-case font-semibold text-sky-600 dark:text-sky-400">
              {' '}
              · {totalLabel}
            </span>
          ) : anyRunning ? (
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
