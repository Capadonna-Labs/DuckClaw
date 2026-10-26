'use client';

import { useEffect } from 'react';
import { ensureWebPushSubscription } from '@/lib/webPushClient';

/** Opening the app = alerts seen: clear the icon badge and the delivered notifications. */
function clearAppBadge() {
  const nav = navigator as Navigator & { clearAppBadge?: () => Promise<void> };
  void nav.clearAppBadge?.().catch(() => undefined);
  void navigator.serviceWorker?.ready
    .then((reg) => reg.getNotifications())
    .then((list) => list.forEach((n) => n.close()))
    .catch(() => undefined);
}

export function PwaServiceWorker() {
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;
    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') return;
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        void registration.update();
        if ('Notification' in window && Notification.permission === 'granted') {
          void ensureWebPushSubscription();
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const sync = () => {
      if (document.visibilityState === 'visible') clearAppBadge();
    };
    sync();
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('focus', sync);
    return () => {
      document.removeEventListener('visibilitychange', sync);
      window.removeEventListener('focus', sync);
    };
  }, []);

  return null;
}
