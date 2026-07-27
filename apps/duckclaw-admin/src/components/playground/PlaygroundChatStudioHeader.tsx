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
    <header className="flex shrink-0 items-center gap-3 border-b border-gov-gray-100 py-3 pl-14 pr-4 sm:pl-[7.75rem] dark:border-dark-border">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {onRenameConversation ? (
          <EditableConversationTitle
            value={displayTitle}
            onSave={onRenameConversation}
            variant="studio"
            className="min-w-0 flex-1"
          />
        ) : (
          <h2 className="min-w-0 flex-1 truncate text-base font-medium text-gov-gray-900 dark:text-dark-text">
            {displayTitle}
          </h2>
        )}
        {tokenLabel ? (
          <span
            className="shrink-0 text-xs tabular-nums text-gov-gray-500 dark:text-dark-muted"
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
