'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMsg } from '@/components/chat/types';
import {
  countUnreadAssistantMessages,
  formatUnreadBadge,
  markReadMessageIndex,
  readLastRead,
  writeLastRead,
} from '@/lib/chatUnreadStorage';
import {
  isChatPanelActivelyViewed,
  isDocumentInBackground,
  notificationPermission,
  notificationsSupported,
  requestNotificationPermission,
  shouldNotifyInBackground,
  showChatNotification,
  snippetFromMessage,
} from '@/lib/chatNotifications';

export type UseFloatingChatUnreadOptions = {
  sessionId: string | null;
  messages: ChatMsg[];
  panelOpen: boolean;
  /** True mientras el asistente genera respuesta (SSE en curso). */
  loading?: boolean;
  historyLoading?: boolean;
  sectionTitle?: string;
  workerLabel?: string;
  onOpenPanel?: () => void;
};

function lastAssistantSnippet(messages: ChatMsg[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'assistant' && !m.streaming && m.text.trim()) {
      return snippetFromMessage(m.text);
    }
  }
  return 'Nuevo mensaje del asistente';
}

function lastCompleteAssistantIndex(messages: ChatMsg[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'assistant' && !m.streaming) return i;
  }
  return -1;
}

export function useFloatingChatUnread({
  sessionId,
  messages,
  panelOpen,
  loading = false,
  historyLoading = false,
  sectionTitle = '',
  workerLabel = '',
  onOpenPanel,
}: UseFloatingChatUnreadOptions) {
  const [unreadCount, setUnreadCount] = useState(0);
  const lastReadRef = useRef(-1);
  const initializedRef = useRef<string | null>(null);
  const prevUnreadRef = useRef(0);
  const permissionAskedRef = useRef(false);
  const lastNotifiedAssistantIndexRef = useRef(-1);
  const pendingNotifyRef = useRef(false);
  const panelOpenRef = useRef(panelOpen);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const syncUnreadFromMessages = useCallback(
    (msgs: ChatMsg[], lastReadIndex: number) => {
      const count = countUnreadAssistantMessages(msgs, lastReadIndex);
      setUnreadCount(count);
      return count;
    },
    []
  );

  const markConversationRead = useCallback(
    (msgs: ChatMsg[]) => {
      if (!sessionId) return;
      const idx = markReadMessageIndex(msgs);
      lastReadRef.current = idx;
      writeLastRead(sessionId, idx);
      setUnreadCount(0);
      prevUnreadRef.current = 0;
      pendingNotifyRef.current = false;
    },
    [sessionId]
  );

  useEffect(() => {
    if (!sessionId) {
      setUnreadCount(0);
      initializedRef.current = null;
      return;
    }

    if (initializedRef.current !== sessionId) {
      initializedRef.current = sessionId;
      prevUnreadRef.current = 0;
      lastNotifiedAssistantIndexRef.current = -1;
      const stored = readLastRead(sessionId);
      if (stored) {
        lastReadRef.current = stored.messageIndex;
      } else if (!historyLoading && messages.length > 0) {
        const idx = markReadMessageIndex(messages);
        lastReadRef.current = idx;
        writeLastRead(sessionId, idx);
      } else {
        lastReadRef.current = -1;
      }
    }

    if (isChatPanelActivelyViewed(panelOpen)) {
      if (!historyLoading) {
        markConversationRead(messages);
      }
      return;
    }

    if (!historyLoading) {
      const stored = readLastRead(sessionId);
      const lastRead = stored?.messageIndex ?? lastReadRef.current;
      lastReadRef.current = lastRead;
      syncUnreadFromMessages(messages, lastRead);
    }
  }, [
    sessionId,
    messages,
    panelOpen,
    historyLoading,
    markConversationRead,
    syncUnreadFromMessages,
  ]);

  panelOpenRef.current = panelOpen;

  const tryShowUnreadNotification = useCallback(
    async (
      msgs: ChatMsg[],
      opts?: { forceBackground?: boolean; panelClosed?: boolean }
    ) => {
      const assistantIdx = lastCompleteAssistantIndex(msgs);
      const count = sessionId
        ? countUnreadAssistantMessages(msgs, lastReadRef.current)
        : 0;
      const perm = notificationPermission();
      const panelClosed =
        opts?.panelClosed ?? !panelOpenRef.current;
      const tabHidden = opts?.forceBackground ?? shouldNotifyInBackground();
      const shouldNotify = tabHidden || panelClosed;
      const visibility =
        typeof document !== 'undefined' ? document.visibilityState : 'unknown';
      const hasFocus =
        typeof document !== 'undefined' ? document.hasFocus() : false;

      if (!sessionId || historyLoading) {
        return;
      }
      if (count <= 0) {
        pendingNotifyRef.current = false;
        return;
      }

      if (!shouldNotify) {
        pendingNotifyRef.current = true;
        return;
      }

      if (perm === 'default' && !permissionAskedRef.current) {
        pendingNotifyRef.current = true;
        return;
      }
      if (perm !== 'granted') {
        pendingNotifyRef.current = false;
        return;
      }

      if (assistantIdx < 0 || assistantIdx <= lastNotifiedAssistantIndexRef.current) {
        return;
      }

      const section = (sectionTitle || '').trim();
      const worker = (workerLabel || '').trim();
      const titleParts = ['DuckClaw'];
      if (section && section !== 'DuckClaw Admin') titleParts.push(section);
      if (worker) titleParts.push(worker);

      const shown = showChatNotification(
        {
          title: titleParts.join(' · '),
          body: lastAssistantSnippet(msgs),
          tag: `duckclaw-chat-${sessionId}`,
          onClick: () => onOpenPanel?.(),
        },
        { requireBackground: false }
      );
      if (shown) {
        lastNotifiedAssistantIndexRef.current = assistantIdx;
        pendingNotifyRef.current = false;
      }
    },
    [sessionId, historyLoading, sectionTitle, workerLabel, onOpenPanel]
  );

  useEffect(() => {
    if (!sessionId || historyLoading || loading) return;
    void tryShowUnreadNotification(messages, { panelClosed: !panelOpenRef.current });
  }, [sessionId, historyLoading, loading, messages, tryShowUnreadNotification]);

  useEffect(() => {
    if (!sessionId || historyLoading) return;
    if (isChatPanelActivelyViewed(panelOpen)) return;

    const count = countUnreadAssistantMessages(messages, lastReadRef.current);
    setUnreadCount(count);
    const gained = count - prevUnreadRef.current;
    prevUnreadRef.current = count;

    if (gained <= 0) return;
    void tryShowUnreadNotification(messages);
  }, [
    sessionId,
    messages,
    panelOpen,
    historyLoading,
    tryShowUnreadNotification,
  ]);

  useEffect(() => {
    if (!sessionId) return;

    const onHide = () => {
      if (!isDocumentInBackground() && !pendingNotifyRef.current) return;
      void tryShowUnreadNotification(messages, { forceBackground: true });
    };

    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', onHide);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      window.removeEventListener('pagehide', onHide);
    };
  }, [sessionId, messages, tryShowUnreadNotification]);

  const ensureNotificationPermission = useCallback(async () => {
    if (!notificationsSupported()) return notificationPermission();
    let perm = notificationPermission();
    if (perm === 'default' && !permissionAskedRef.current) {
      permissionAskedRef.current = true;
      perm = await requestNotificationPermission();
    }
    if (perm === 'granted' && sessionId && !historyLoading) {
      void tryShowUnreadNotification(messagesRef.current, {
        panelClosed: !panelOpenRef.current,
        forceBackground: shouldNotifyInBackground(),
      });
    }
    return perm;
  }, [sessionId, historyLoading, tryShowUnreadNotification]);

  const badgeLabel =
    unreadCount > 0
      ? `${unreadCount} mensaje${unreadCount === 1 ? '' : 's'} sin leer`
      : undefined;

  const notificationPermissionState = notificationPermission();

  return {
    unreadCount,
    badgeText: formatUnreadBadge(unreadCount),
    badgeLabel,
    markConversationRead,
    ensureNotificationPermission,
    notificationPermission: notificationPermissionState,
  };
}
