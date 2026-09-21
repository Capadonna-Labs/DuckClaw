'use client';

import { useEffect } from 'react';
import { ensureWebPushSubscription } from '@/lib/webPushClient';
import { mutationHeaders } from '@/lib/csrfClient';

function reportPwaPresence(visible: boolean) {
  void fetch('/api/admin/notifications/pwa-presence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...mutationHeaders('POST') },
    body: JSON.stringify({ visible }),
    keepalive: true,
  }).catch(() => undefined);
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
    const visible = () => document.visibilityState === 'visible';
    const sync = () => reportPwaPresence(visible());
    sync();
    const timer = window.setInterval(() => {
      if (visible()) reportPwaPresence(true);
    }, 15_000);
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('focus', sync);
    window.addEventListener('blur', sync);
    window.addEventListener('pagehide', () => reportPwaPresence(false));
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', sync);
      window.removeEventListener('focus', sync);
      window.removeEventListener('blur', sync);
      reportPwaPresence(false);
    };
  }, []);

  return null;
}
