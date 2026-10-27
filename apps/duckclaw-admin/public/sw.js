self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Home-screen icon badge = notifications not opened yet (iOS 16.4+ PWA, Android, desktop).
// The page clears it when the app comes to the foreground (PwaServiceWorker.tsx).
function syncAppBadge() {
  if (!self.navigator || !self.navigator.setAppBadge) return Promise.resolve();
  return self.registration
    .getNotifications()
    .then((list) => (list.length ? self.navigator.setAppBadge(list.length) : self.navigator.clearAppBadge()))
    .catch(() => undefined);
}

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { body: event.data ? event.data.text() : '' };
  }

  const title = payload.title || 'DuckClaw';
  const options = {
    body: payload.body || 'Nueva alerta de DuckClaw',
    icon: '/icons/icon-192.png',
    badge: '/icons/badge-96.png',
    tag: payload.tag || 'duckclaw-alert',
    data: { url: payload.url || '/login' },
  };

  // Always shown: whether to send is decided by the "Notificaciones" switch (server side), not by what is on screen.
  event.waitUntil(self.registration.showNotification(title, options).then(syncAppBadge));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/login';
  event.waitUntil(Promise.all([syncAppBadge(), clients.openWindow(url)]));
});
