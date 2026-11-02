'use client';

import { useCallback, useEffect, useState } from 'react';
import { requestNotificationPermission } from '@/lib/chatNotifications';
import { ensureWebPushSubscription, isChatMuted, setChatMuted } from '@/lib/webPushClient';

function readLocalFlag(key: string, defaultValue: boolean): boolean {
  if (typeof window === 'undefined') return defaultValue;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw == null) return defaultValue;
    return raw !== '0';
  } catch {
    return defaultValue;
  }
}

function writeLocalFlag(key: string, enabled: boolean): void {
  try {
    window.localStorage.setItem(key, enabled ? '1' : '0');
  } catch {
    /* ignore quota */
  }
}

/** Playground toggles persisted in localStorage: suggestions, and notifications, which are per chat (a muted chat does not silence the others or the system alerts). */
export function usePlaygroundChatToggles(chatId: string) {
  const [suggestionsEnabled, setSuggestionsEnabled] = useState(() =>
    readLocalFlag('duckclaw.chat.suggestionsEnabled', true)
  );
  const [notificationsEnabled, setNotificationsEnabled] = useState(() => !isChatMuted(chatId));
  useEffect(() => {
    setNotificationsEnabled(!isChatMuted(chatId));
  }, [chatId]);

  const handleSuggestionsToggle = useCallback(() => {
    setSuggestionsEnabled((prev) => {
      const next = !prev;
      writeLocalFlag('duckclaw.chat.suggestionsEnabled', next);
      return next;
    });
  }, []);

  const handleNotificationsToggle = useCallback(() => {
    setNotificationsEnabled((prev) => {
      const next = !prev;
      setChatMuted(chatId, !next);
      if (next) void requestNotificationPermission();
      void ensureWebPushSubscription(); // tells the server which chats this device muted
      return next;
    });
  }, [chatId]);

  return {
    suggestionsEnabled,
    notificationsEnabled,
    handleSuggestionsToggle,
    handleNotificationsToggle,
  };
}
