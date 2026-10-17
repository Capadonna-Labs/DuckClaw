'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePipecatLiveVoice } from '@/components/chat/usePipecatLiveVoice';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { clearPendingDetachedTurn, writePendingDetachedTurn } from '@/lib/detachedTurnState';
import type { AdminChatController } from '@/components/chat/useAdminChat';

type Options = Pick<
  AdminChatController,
  | 'config'
  | 'workerId'
  | 'messages'
  | 'vaultPath'
  | 'liveVoiceAvailable'
  | 'reloadHistory'
  | 'setMessages'
  | 'showScrollButton'
  | 'scrollToBottom'
> & {
  chatId: string;
  sectionTitle?: string;
  isCompact: boolean;
};

/** Live voice call for the admin chat: spoken turns show in the chat while the call is on. */
export function useAdminChatLiveVoice({
  chatId,
  sectionTitle,
  isCompact,
  config,
  workerId,
  messages,
  vaultPath,
  liveVoiceAvailable,
  reloadHistory,
  setMessages,
  showScrollButton,
  scrollToBottom,
}: Options) {
  // Show the spoken turn (user bubble, tool usage, reply) while the call is on, not only
  // after hanging up. Poll history while the agent works, then once more when done.
  const [voiceGraphBusy, setVoiceGraphBusy] = useState(false);
  const voiceUserTextRef = useRef('');
  const tenantId = (config?.effective_tenant_id || 'default').trim() || 'default';
  const liveVoice = usePipecatLiveVoice({
    enabled: liveVoiceAvailable,
    onDisconnected: () => {
      setVoiceGraphBusy(false);
      clearPendingDetachedTurn(chatId);
      reloadHistory();
    },
    onGraphPhaseChange: (phase) => {
      const busy = phase === 'graph';
      setVoiceGraphBusy(busy);
      const spoken = voiceUserTextRef.current.trim();
      if (busy && spoken) {
        // Show the spoken turn now (it is only persisted with the reply) so its tool
        // bubbles anchor to it instead of piling onto the previous turn's block.
        writePendingDetachedTurn({ chatId, tenantId, workerId, text: spoken, startedAt: Date.now() });
        setMessages((prev) => [...prev, { role: 'user', text: spoken }]);
      }
      reloadHistory({ force: true });
      // The turn is persisted right after the reply; a second read catches a slow write.
      if (!busy) {
        window.setTimeout(() => {
          clearPendingDetachedTurn(chatId);
          reloadHistory({ force: true });
        }, 1500);
      }
    },
  });
  voiceUserTextRef.current = liveVoice.userSubtitle;
  // ponytail: 2 s polling while the agent works; push via SSE if it ever feels laggy.
  useVisibilityAwareInterval(() => reloadHistory({ force: true }), voiceGraphBusy ? 2000 : null);
  // During a call keep the newest bubble in view above the voice bar (unless the user scrolled up).
  useEffect(() => {
    if (!liveVoice.isActive || showScrollButton) return;
    requestAnimationFrame(() => scrollToBottom('smooth'));
  }, [liveVoice.isActive, messages.length, showScrollButton, scrollToBottom]);

  const voiceAppState = useMemo(
    () => ({
      chat_id: chatId,
      worker_id: workerId,
      tenant_id: tenantId,
      vault_path: vaultPath || undefined,
      section: sectionTitle,
      variant: isCompact ? ('bubble' as const) : ('playground' as const),
    }),
    [chatId, workerId, tenantId, vaultPath, sectionTitle, isCompact]
  );

  useEffect(() => {
    if (liveVoice.isConnected) {
      void liveVoice.endCall();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- colgar al cambiar conversación o worker
  }, [chatId, workerId]);

  useEffect(() => {
    if (!liveVoice.isConnected) return;
    liveVoice.sendAppState(voiceAppState);
  }, [liveVoice, liveVoice.isConnected, voiceAppState]);

  const handleLiveVoiceClick = useCallback(async () => {
    if (!workerId || !chatId) return;
    await liveVoice.toggleCall(voiceAppState);
  }, [chatId, liveVoice, voiceAppState, workerId]);

  return { liveVoice, handleLiveVoiceClick };
}
