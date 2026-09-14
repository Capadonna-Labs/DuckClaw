'use client';

import type { ReactNode } from 'react';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import { TokenConsumptionMenu } from '@/components/chat/TokenConsumptionMenu';
import type { UsageTokenBreakdown } from '@/lib/formatTokenCount';
import type { ContextTokenBreakdown } from '@/lib/contextTokenBreakdown';

type PlaygroundChatStudioHeaderProps = {
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  tokenUsage?: UsageTokenBreakdown | null;
  contextEstimatedTokens?: number | null;
  contextTokenBreakdown?: ContextTokenBreakdown | null;
  /** Modelo LLM activo (para estimar ventana de contexto). */
  model?: string | null;
  fallbackTitle?: string;
  /** Botón volver u otras acciones a la izquierda (misma fila, centradas). */
  leading?: ReactNode;
  /** Acciones a la derecha (sandbox, logs, settings). */
  trailing?: ReactNode;
};

/** Cabecera estilo AI Studio: título editable + botón de consumo (estilo Claude). */
export function PlaygroundChatStudioHeader({
  conversationTitle,
  onRenameConversation,
  tokenUsage = null,
  contextEstimatedTokens = null,
  contextTokenBreakdown = null,
  model = null,
  fallbackTitle = 'Nueva conversación',
  leading,
  trailing,
}: PlaygroundChatStudioHeaderProps) {
  const displayTitle = (conversationTitle || '').trim() || fallbackTitle;

  return (
    <header className="studio-glass-chrome flex min-h-14 shrink-0 items-center gap-2 border-b px-2.5 py-2 sm:gap-3 sm:px-4 sm:py-2.5">
      {leading ? <div className="flex shrink-0 items-center gap-1">{leading}</div> : null}
      <div className="flex min-w-0 flex-1 flex-col justify-center">
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
      </div>
      <TokenConsumptionMenu
        tokenUsage={tokenUsage}
        contextEstimatedTokens={contextEstimatedTokens}
        contextTokenBreakdown={contextTokenBreakdown}
        model={model}
      />
      {trailing ? <div className="flex shrink-0 items-center gap-1">{trailing}</div> : null}
    </header>
  );
}
