'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';
import type { ChatMsg } from '@/components/chat/types';

export function ChatBubble({ message: m }: { message: ChatMsg }) {
  const isUser = m.role === 'user';
  const isError = m.role === 'error';
  const isInterrupted = Boolean(m.interrupted);

  return (
    <div
      className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm ${
        isUser
          ? 'ml-auto bg-gov-blue-700 text-white'
          : isError
            ? 'bg-red-50 text-red-800 border border-red-200 whitespace-pre-wrap dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
            : isInterrupted
              ? 'bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200'
              : 'bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border'
      }`}
    >
      {isUser || isError || isInterrupted ? (
        <span className="whitespace-pre-wrap">{m.text}</span>
      ) : (
        <>
          <ChatMarkdown content={m.text} />
          {m.streaming && m.text && (
            <span className="inline-block w-2 h-4 ml-0.5 bg-gov-blue-600 animate-pulse align-middle" />
          )}
        </>
      )}
    </div>
  );
}

export function ThinkingBubble({ startedAt }: { startedAt: number }) {
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    const update = () => {
      const raw = Math.max(0, (Date.now() - startedAt) / 1000);
      setElapsedSec(Math.round(raw * 10) / 10);
    };
    update();
    const id = window.setInterval(update, 100);
    return () => window.clearInterval(id);
  }, [startedAt]);

  return (
    <div
      className="max-w-[85%] flex items-center gap-3 rounded-2xl px-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border"
      role="status"
      aria-live="polite"
      aria-label={`Pensando, ${elapsedSec.toFixed(1)} segundos`}
    >
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        <span className="absolute inset-0 rounded-full border-2 border-gov-blue-200 dark:border-gov-blue-900" />
        <Loader2 className="h-6 w-6 animate-spin text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
      </div>
      <p className="text-sm font-semibold text-gov-gray-700 dark:text-dark-text">Pensando…</p>
    </div>
  );
}
