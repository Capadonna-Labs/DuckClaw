'use client';

import type { ReactNode } from 'react';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import {
  formatTokenCount,
  formatUsageTokensLogLine,
  type UsageTokenBreakdown,
} from '@/lib/formatTokenCount';

type PlaygroundChatStudioHeaderProps = {
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  tokenUsage?: UsageTokenBreakdown | null;
  contextEstimatedTokens?: number | null;
  fallbackTitle?: string;
  /** Botón volver u otras acciones a la izquierda (misma fila, centradas). */
  leading?: ReactNode;
  /** Acciones a la derecha (sandbox, logs, settings). */
  trailing?: ReactNode;
};

/** Cabecera estilo AI Studio: título editable + tokens del último turno (misma línea que gateway logs). */
export function PlaygroundChatStudioHeader({
  conversationTitle,
  onRenameConversation,
  tokenUsage = null,
  contextEstimatedTokens = null,
  fallbackTitle = 'Nueva conversación',
  leading,
  trailing,
}: PlaygroundChatStudioHeaderProps) {
  const displayTitle = (conversationTitle || '').trim() || fallbackTitle;
  const tokenLabel = tokenUsage
    ? formatUsageTokensLogLine(tokenUsage)
    : contextEstimatedTokens != null && contextEstimatedTokens > 0
      ? `${formatTokenCount(contextEstimatedTokens)} (est.)`
      : null;

  return (
    <header className="studio-glass-chrome flex min-h-14 shrink-0 items-center gap-2 border-b px-2.5 py-2 sm:gap-3 sm:px-4 sm:py-2.5">
      {leading ? <div className="flex shrink-0 items-center gap-1">{leading}</div> : null}
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
        {onRenameConversation ? (
          <EditableConversationTitle
            value={displayTitle}
            onSave={onRenameConversation}
            variant="studio"
            className="min-w-0 w-full"
          />
        ) : (
          <h2 className="min-w-0 truncate text-base font-medium leading-tight text-gov-gray-900 dark:text-dark-text">
            {displayTitle}
          </h2>
        )}
        {tokenLabel ? (
          <span
            className="max-w-full truncate text-[10px] leading-none tabular-nums text-gov-gray-500 dark:text-dark-muted"
            title={
              tokenUsage
                ? 'Tokens del último turno (igual que gateway logs: Total [P:prompt, C:completion])'
                : 'Tokens estimados del contexto tras compactar el hilo'
            }
          >
            {tokenLabel}
          </span>
        ) : null}
      </div>
      {trailing ? <div className="flex shrink-0 items-center gap-1">{trailing}</div> : null}
    </header>
  );
}
