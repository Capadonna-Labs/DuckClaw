'use client';

import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { formatTokenCount } from '@/lib/formatTokenCount';

type PlaygroundChatStudioHeaderProps = {
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  tokenTotal?: number;
  contextEstimated?: boolean;
  fallbackTitle?: string;
};

/** Cabecera estilo AI Studio: título editable + contador de tokens de sesión. */
export function PlaygroundChatStudioHeader({
  conversationTitle,
  onRenameConversation,
  tokenTotal = 0,
  contextEstimated = false,
  fallbackTitle = 'Nueva conversación',
}: PlaygroundChatStudioHeaderProps) {
  const displayTitle = (conversationTitle || '').trim() || fallbackTitle;

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
        <span
          className="shrink-0 text-xs tabular-nums text-gov-gray-500 dark:text-dark-muted"
          title={
            contextEstimated
              ? 'Tokens estimados del contexto activo tras compactar el hilo'
              : 'Tokens acumulados en esta conversación (turnos con métricas del LLM)'
          }
        >
          {formatTokenCount(tokenTotal)}
        </span>
      </div>
    </header>
  );
}
