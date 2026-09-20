'use client';

import { useEffect } from 'react';
import { ensureWebPushSubscription } from '@/lib/webPushClient';

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

  return null;
}
