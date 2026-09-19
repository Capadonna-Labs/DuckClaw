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
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    tag: payload.tag || 'duckclaw-alert',
    data: { url: payload.url || '/login' },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/login';
  event.waitUntil(clients.openWindow(url));
});
