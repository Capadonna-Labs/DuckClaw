'use client';

import { useEffect, useState } from 'react';
import type { ChatMsg } from '@/components/chat/types';
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

  useEffect(() => {
    if (!running) {
      setLiveMs(m.toolElapsedMs ?? null);
      return;
    }
    const t0 = m.toolStartedAt ?? Date.now();
    const tick = () => setLiveMs(Math.max(0, Date.now() - t0));
    tick();
    const id = window.setInterval(tick, 50);
    return () => window.clearInterval(id);
  }, [running, m.toolStartedAt, m.toolElapsedMs, m.toolPhase]);

  const durMs = running ? liveMs : (m.toolElapsedMs ?? liveMs);
  const dur = formatToolDurationMs(durMs);
  const isError = m.toolPhase === 'error';

  return (
    <li className="px-3 py-1.5 text-sm text-sky-950 dark:text-sky-100">
      <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
        {`Usando: ${toolName}`}
        {isError ? ' · error' : ''}
        {dur ? ` · ${dur}` : running ? ' · en curso' : ''}
      </span>
    </li>
  );
}
