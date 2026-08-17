'use client';

import { ChevronDown } from 'lucide-react';
import { ChatBubble, ThinkingBubble } from '@/components/chat/ChatBubble';
import { ToolUsageGroup } from '@/components/chat/ToolUsageGroup';
import type { ChatMsg } from '@/components/chat/types';
import {
  hasToolHeartbeatInCurrentTurn,
  isThinkingStatusHeartbeat,
  shouldSkipEmptyStreamingAssistant,
} from '@/components/chat/useAdminChat';
import { groupMessagesForDisplay, toolGroupStableKey } from '@/lib/toolUsageGroup';
import type { RefObject } from 'react';

export type AdminChatMessageListProps = {
  messages: ChatMsg[];
  emptyHint?: string;
  workerId: string;
  workerDisplayName: string;
  thinking: boolean;
  thinkingStartedAt: RefObject<number>;
  thinkingIdentity: { workerId: string; swarmSlot: number };
  labelForWorkerId: (id?: string) => string;
  loading: boolean;
  /** Muestra u oculta el detalle de invocaciones de herramientas del chat. */
  showToolUsage?: boolean;
  isCompact: boolean;
  scrollRef: RefObject<HTMLDivElement>;
  showScrollButton: boolean;
  onScroll: () => void;
  scrollToBottom: (behavior?: ScrollBehavior) => void;
  retryFromMessage: (index: number) => void;
  editFromMessage: (index: number) => void;
};

function renderMessageBubble(
  messages: ChatMsg[],
  i: number,
  opts: {
    workerId: string;
    loading: boolean;
    labelForWorkerId: (id?: string) => string;
    retryFromMessage: (index: number) => void;
    editFromMessage: (index: number) => void;
  }
) {
  const m = messages[i];
  const prevUserIdx =
    m.role === 'assistant' && !m.streaming
      ? (() => {
          for (let j = i - 1; j >= 0; j--) {
            if (messages[j]?.role === 'user') return j;
          }
          return -1;
        })()
      : -1;
  return (
    <ChatBubble
      key={
        m.toolInvocationId
          ? `${i}-${m.role}-${m.toolInvocationId}`
          : `${i}-${m.role}`
      }
      message={m}
      identityLabel={opts.labelForWorkerId(m.workerId || opts.workerId)}
      activeWorkerId={opts.workerId}
      canRetry={
        !opts.loading &&
        ((m.role === 'user' &&
          (Boolean(m.text?.trim()) || Boolean(m.imagePreviews?.length))) ||
          (m.role === 'assistant' && prevUserIdx >= 0))
      }
      onRetry={
        m.role === 'user'
          ? () => void opts.retryFromMessage(i)
          : m.role === 'assistant' && prevUserIdx >= 0
            ? () => void opts.retryFromMessage(prevUserIdx)
            : undefined
      }
      canEdit={!opts.loading && m.role === 'user' && Boolean(m.text?.trim())}
      onEdit={m.role === 'user' ? () => opts.editFromMessage(i) : undefined}
    />
  );
}

export function AdminChatMessageList({
  messages,
  emptyHint,
  workerId,
  workerDisplayName,
  thinking,
  thinkingStartedAt,
  thinkingIdentity,
  labelForWorkerId,
  loading,
  showToolUsage = true,
  isCompact,
  scrollRef,
  showScrollButton,
  onScroll,
  scrollToBottom,
  retryFromMessage,
  editFromMessage,
}: AdminChatMessageListProps) {
  const displayItems = groupMessagesForDisplay(messages);
  const bubbleOpts = {
    workerId,
    loading,
    labelForWorkerId,
    retryFromMessage,
    editFromMessage,
  };

  return (
      <div className="relative flex-1 min-h-0 min-w-0 flex flex-col w-full">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className={`scrollbar-thin flex-1 overflow-y-auto overflow-x-hidden p-3 space-y-3 min-h-0 w-full ${
            isCompact ? '' : 'min-h-[320px]'
          }`}
        >
        {messages.length === 0 && (
          <p className="text-sm text-gov-gray-400 text-center py-8">
            {emptyHint ??
              (workerId
                ? `Escribe un mensaje para hablar con ${workerDisplayName}`
                : 'Escribe un mensaje para hablar con …')}
          </p>
        )}
        {displayItems.map((item, itemIdx) => {
          if (item.kind === 'toolGroup') {
            if (!showToolUsage) return null;
            const firstIdx = item.indices[0];
            const first = messages[firstIdx];
            return (
              <ToolUsageGroup
                key={toolGroupStableKey(messages, item.indices)}
                messages={messages}
                indices={item.indices}
                identityLabel={labelForWorkerId(first?.workerId || workerId)}
              />
            );
          }

          const i = item.index;
          const m = messages[i];
          const next = messages[i + 1];
          if (
            isThinkingStatusHeartbeat(m) &&
            next?.role === 'assistant' &&
            next.streaming &&
            !next.text &&
            thinking
          ) {
            return null;
          }
          const isEmptyStreaming =
            m.role === 'assistant' && m.streaming && !m.text && thinking && i === messages.length - 1;
          if (
            isEmptyStreaming &&
            (!showToolUsage || !hasToolHeartbeatInCurrentTurn(messages))
          ) {
            return (
              <ThinkingBubble
                key={`${i}-thinking`}
                startedAt={thinkingStartedAt.current || Date.now()}
                identityLabel={labelForWorkerId(thinkingIdentity.workerId || workerId)}
              />
            );
          }
          if (shouldSkipEmptyStreamingAssistant(m, messages)) {
            return null;
          }
          return renderMessageBubble(messages, i, bubbleOpts);
        })}
        </div>
        {showScrollButton && (
          <button
            type="button"
            onClick={() => scrollToBottom('smooth')}
            className="absolute bottom-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-gov-blue-700 text-white shadow-lg ring-2 ring-white/80 hover:bg-gov-blue-800 dark:ring-dark-surface max-lg:bottom-16"
            aria-label="Ir al final de la conversación"
            title="Ir abajo"
          >
            <ChevronDown size={20} aria-hidden />
          </button>
        )}
      </div>
  );
}
