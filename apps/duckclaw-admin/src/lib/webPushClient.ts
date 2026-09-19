function urlBase64ToArrayBuffer(value: string): ArrayBuffer {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = `${value}${padding}`.replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const out = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return buffer;
}

export async function ensureWebPushSubscription(): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return false;
  if (!('Notification' in window) || Notification.permission !== 'granted') return false;
  if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') return false;

  try {
    const keyRes = await fetch('/api/admin/notifications/web-push/public-key', { cache: 'no-store' });
    if (!keyRes.ok) return false;
    const keyJson = (await keyRes.json()) as { public_key?: string; subscribe_enabled?: boolean };
    const publicKey = (keyJson.public_key || '').trim();
    if (!publicKey || !keyJson.subscribe_enabled) return false;

    const registration = await navigator.serviceWorker.ready;
    const existing = await registration.pushManager.getSubscription();
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToArrayBuffer(publicKey),
      }));

    const res = await fetch('/api/admin/notifications/web-push/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subscription: subscription.toJSON(),
        device_label: navigator.userAgent.slice(0, 120),
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}