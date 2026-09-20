'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ChatMsg } from '@/components/chat/types';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import {
  formatToolDisplayName,
  formatToolDurationMs,
  parseToolNameFromHeartbeatText,
} from '@/lib/toolHeartbeat';

export function ToolHeartbeatRow({ message: m }: { message: ChatMsg }) {
  const toolName = formatToolDisplayName(
    (m.toolName || '').trim() || parseToolNameFromHeartbeatText(m.text || '') || 'tool'
  );
  const running =
    m.toolPhase === 'running' ||
    m.toolPhase === 'start' ||
    (m.heartbeatKind === 'tool' && m.toolPhase !== 'done' && m.toolPhase !== 'error');
  const [liveMs, setLiveMs] = useState<number | null>(null);
  const [fallbackStartedAt] = useState(() => Date.now());
  const t0 = m.toolStartedAt ?? fallbackStartedAt;
  const tick = useCallback(() => {
    if (!running) {
      setLiveMs(m.toolElapsedMs ?? null);
      return;
    }
    setLiveMs(Math.max(0, Date.now() - t0));
  }, [m.toolElapsedMs, running, t0]);

  useEffect(() => {
    tick();
  }, [tick]);

  useVisibilityAwareInterval(tick, running ? 50 : null);

  const durMs = running ? liveMs : (m.toolElapsedMs ?? liveMs);
  const dur = formatToolDurationMs(durMs);
  const isError = m.toolPhase === 'error';

  return (
    <li className="px-3 py-1.5 text-sm text-sky-950 dark:text-sky-100">
      <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
        {toolName}
        {isError ? ' · error' : ''}
        {dur ? ` · ${dur}` : running ? ' · en curso' : ''}
      </span>
    </li>
  );
}
