import { mutationHeaders } from '@/lib/csrfClient';

function urlBase64ToArrayBuffer(value: string): ArrayBuffer {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = `${value}${padding}`.replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const out = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return buffer;
}

const PREF_KEY = 'duckclaw.chat.notificationsEnabled';

/** The "Notificaciones" switch of this device (default on). */
export function notificationsPreference(): boolean {
  try {
    return window.localStorage.getItem(PREF_KEY) !== '0';
  } catch {
    return true;
  }
}

/** Registers this device's push subscription and tells the server whether the switch is on; with the switch off an existing subscription is only marked off. */
export async function ensureWebPushSubscription(enabled: boolean = notificationsPreference()): Promise<boolean> {
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
    if (!enabled && !existing) return false;
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToArrayBuffer(publicKey),
      }));

    const res = await fetch('/api/admin/notifications/web-push/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...mutationHeaders('POST') },
      body: JSON.stringify({
        subscription: subscription.toJSON(),
        device_label: navigator.userAgent.slice(0, 120),
        enabled,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}