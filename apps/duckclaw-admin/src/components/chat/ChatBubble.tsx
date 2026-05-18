'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Loader2 } from 'lucide-react';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';
import type { ChatMsg } from '@/components/chat/types';

export function formatChatIdentityPrefix(workerId?: string, swarmSlot = 1): string {
  const slot = Number.isFinite(swarmSlot) && swarmSlot >= 1 ? Math.floor(swarmSlot) : 1;
  const workerLabel = (workerId || '').trim();
  return workerLabel ? `${workerLabel} ${slot}` : String(slot);
}

/** Quita prefijo duplicado en heartbeat (UI ya muestra worker + tipo). */
export function stripHeartbeatBodyPrefix(
  text: string,
  workerId?: string,
  swarmSlot = 1
): string {
  let body = (text || '').trim();
  if (!body) return body;

  const identity = formatChatIdentityPrefix(workerId, swarmSlot);
  if (identity) {
    const esc = identity.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    body = body.replace(new RegExp(`^${esc}(?:\\s*[—–-]\\s*)?`, 'u'), '').trim();
  }

  const workerBase = (workerId || '').trim();
  if (workerBase) {
    const escBase = workerBase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    body = body
      .replace(new RegExp(`^\\*\\*${escBase}(?:\\s+\\d+)?\\s*·[^*]+\\*\\*\\s*`, 'iu'), '')
      .trim();
  }
  return body;
}

export function ChatBubble({ message: m }: { message: ChatMsg }) {
  const isUser = m.role === 'user';
  const isError = m.role === 'error';
  const isHeartbeat = m.role === 'heartbeat';
  const isInterrupted = Boolean(m.interrupted);
  const displayText =
    isHeartbeat && m.text
      ? stripHeartbeatBodyPrefix(m.text, m.workerId, m.swarmSlot ?? 1)
      : m.text;
  const canCopy = Boolean(displayText?.trim()) && !m.streaming;
  const [copied, setCopied] = useState(false);
  const heartbeatLabel =
    m.heartbeatKind === 'plan'
      ? 'Plan'
      : m.heartbeatKind === 'tool'
        ? 'Herramienta'
        : 'Progreso';

  const copyText = useCallback(async () => {
    if (!displayText?.trim()) return;
    try {
      await navigator.clipboard.writeText(displayText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  }, [displayText]);

  return (
    <div
      className={`group relative max-w-[90%] min-w-0 rounded-2xl px-4 py-3 text-sm overflow-hidden ${
        isUser
          ? 'ml-auto bg-gov-blue-700 text-white'
          : isError
            ? 'bg-red-50 text-red-800 border border-red-200 whitespace-pre-wrap dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
            : isHeartbeat
              ? 'mx-auto w-full max-w-full bg-sky-50 text-sky-950 border border-sky-200/80 dark:bg-sky-950/25 dark:text-sky-100 dark:border-sky-800/60'
              : isInterrupted
                ? 'bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200'
                : 'bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border'
      } ${canCopy ? 'pr-9' : ''}`}
    >
      {canCopy && (
        <button
          type="button"
          onClick={() => void copyText()}
          className={`absolute top-2 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity p-1 rounded-md ${
            isUser
              ? 'right-2 text-white/80 hover:bg-white/15'
              : 'right-2 text-gov-gray-400 hover:bg-gov-gray-200/80 dark:hover:bg-dark-border'
          }`}
          aria-label={copied ? 'Copiado' : 'Copiar mensaje'}
          title={copied ? 'Copiado' : 'Copiar'}
        >
          {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
        </button>
      )}
      {isHeartbeat && (
        <p className="text-[10px] font-bold uppercase tracking-wider text-sky-700/90 dark:text-sky-300/90 mb-1">
          <span className="normal-case text-sky-800 dark:text-sky-200">
            {formatChatIdentityPrefix(m.workerId, m.swarmSlot ?? 1)}
          </span>
          {' · '}
          {heartbeatLabel}
        </p>
      )}
      {isUser && m.imagePreviews && m.imagePreviews.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${displayText?.trim() ? 'mb-2' : ''}`}>
          {m.imagePreviews.map((img) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={img.url}
              src={img.url}
              alt={img.name}
              className="max-h-32 max-w-full rounded-lg border border-white/20 object-contain"
            />
          ))}
        </div>
      )}
      {isUser || isError || isInterrupted || isHeartbeat ? (
        displayText?.trim() ? (
          <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {displayText}
          </span>
        ) : null
      ) : (
        <>
          <ChatMarkdown content={displayText} />
          {m.streaming && displayText && (
            <span className="inline-block w-2 h-4 ml-0.5 bg-gov-blue-600 animate-pulse align-middle" />
          )}
        </>
      )}
    </div>
  );
}

export type ThinkingBubbleProps = {
  startedAt: number;
  /** Worker activo en el selector (p. ej. finanz, Quant-Trader). */
  workerId?: string;
  /** Instancia swarm 1..n; la base siempre es 1. */
  swarmSlot?: number;
};

export function ThinkingBubble({
  startedAt,
  workerId = '',
  swarmSlot = 1,
}: ThinkingBubbleProps) {
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    const update = () => {
      const raw = Math.max(0, (Date.now() - startedAt) / 1000);
      setElapsedSec(Math.round(raw * 100) / 100);
    };
    update();
    const id = window.setInterval(update, 50);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const elapsedLabel = elapsedSec.toFixed(2);
  const identityPrefix = formatChatIdentityPrefix(workerId, swarmSlot);

  return (
    <div
      className="max-w-[85%] flex items-center gap-3 rounded-2xl px-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border"
      role="status"
      aria-live="polite"
      aria-label={`${identityPrefix} Pensando, ${elapsedLabel} segundos`}
    >
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        <span className="absolute inset-0 rounded-full border-2 border-gov-blue-200 dark:border-gov-blue-900" />
        <Loader2 className="h-6 w-6 animate-spin text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
      </div>
      <p className="text-sm font-semibold text-gov-gray-700 dark:text-dark-text tabular-nums">
        <span className="text-gov-blue-800 dark:text-dark-cyan">{identityPrefix}</span>{' '}
        Pensando…{' '}
        <span className="font-mono text-gov-gray-500 dark:text-dark-muted">{elapsedLabel}s</span>
      </p>
    </div>
  );
}
