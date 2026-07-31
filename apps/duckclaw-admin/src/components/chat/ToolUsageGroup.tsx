'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { ToolHeartbeatRow } from '@/components/chat/ToolHeartbeatRow';
import type { ChatMsg } from '@/components/chat/types';
import { formatChatIdentityPrefix } from '@/lib/workerOptions';
import { formatToolDurationMs } from '@/lib/toolHeartbeat';
import { toolGroupHasRunning, toolGroupTotalElapsedMs } from '@/lib/toolUsageGroup';

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
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const isOpen = userOpen ?? anyRunning;

  const identityPrefix = formatChatIdentityPrefix(identityLabel);
  const count = items.length;
  const totalLabel = totalMs != null ? formatToolDurationMs(totalMs) : '';

  return (
    <div className="mx-auto w-full max-w-full min-w-0 rounded-2xl bg-sky-50 text-sky-950 border border-sky-200/80 dark:bg-sky-950/25 dark:text-sky-100 dark:border-sky-800/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setUserOpen((prev) => !(prev ?? anyRunning))}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
        aria-expanded={isOpen}
        aria-controls={panelId}
      >
        <span className="min-w-0 text-[10px] font-bold uppercase tracking-wider text-sky-700/90 dark:text-sky-300/90">
          <span className="normal-case text-sky-800 dark:text-sky-200">{identityPrefix}</span>
          {' · '}
          Herramientas ({count})
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
          {items.map((m, idx) => (
            <ToolHeartbeatRow
              key={m.toolInvocationId || `${indices[idx]}-${m.toolName || idx}`}
              message={m}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
