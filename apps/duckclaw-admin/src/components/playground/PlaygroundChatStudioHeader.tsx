'use client';

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
};

/** Cabecera estilo AI Studio: título editable + tokens del último turno (misma línea que gateway logs). */
export function PlaygroundChatStudioHeader({
  conversationTitle,
  onRenameConversation,
  tokenUsage = null,
  contextEstimatedTokens = null,
  fallbackTitle = 'Nueva conversación',
}: PlaygroundChatStudioHeaderProps) {
  const displayTitle = (conversationTitle || '').trim() || fallbackTitle;
  const tokenLabel = tokenUsage
    ? formatUsageTokensLogLine(tokenUsage)
    : contextEstimatedTokens != null && contextEstimatedTokens > 0
      ? `${formatTokenCount(contextEstimatedTokens)} (est.)`
      : null;

  return (
    <header className="studio-glass-chrome flex shrink-0 items-center gap-2 border-b py-2.5 pl-12 pr-[7.5rem] sm:gap-3 sm:py-3 sm:pl-14 sm:pr-4">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
        {onRenameConversation ? (
          <EditableConversationTitle
            value={displayTitle}
            onSave={onRenameConversation}
            variant="studio"
            className="min-w-0 w-full sm:flex-1"
          />
        ) : (
          <h2 className="min-w-0 truncate text-sm font-medium text-gov-gray-900 sm:flex-1 sm:text-base dark:text-dark-text">
            {displayTitle}
          </h2>
        )}
        {tokenLabel ? (
          <span
            className="max-w-full truncate text-[10px] tabular-nums text-gov-gray-500 sm:shrink-0 sm:text-xs dark:text-dark-muted"
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
    </header>
  );
}
