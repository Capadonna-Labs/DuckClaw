'use client';

import { useCallback, useState } from 'react';
import { requestNotificationPermission } from '@/lib/chatNotifications';

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

/** Playground toggles persisted in localStorage (suggestions + notifications). */
export function usePlaygroundChatToggles() {
  const [suggestionsEnabled, setSuggestionsEnabled] = useState(() =>
    readLocalFlag('duckclaw.chat.suggestionsEnabled', true)
  );
  const [notificationsEnabled, setNotificationsEnabled] = useState(() =>
    readLocalFlag('duckclaw.chat.notificationsEnabled', true)
  );

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
      writeLocalFlag('duckclaw.chat.notificationsEnabled', next);
      if (next) void requestNotificationPermission();
      return next;
    });
  }, []);

  return {
    suggestionsEnabled,
    notificationsEnabled,
    handleSuggestionsToggle,
    handleNotificationsToggle,
  };
}
