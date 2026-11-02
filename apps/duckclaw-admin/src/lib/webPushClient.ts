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

const MUTED_KEY = 'duckclaw.chat.notificationsMuted';

/** The push tag of a chat: what the server puts on its notifications (see _notify_playground_turn_done). */
export function chatPushTag(chatId: string): string {
  return `duckclaw-playground-${chatId}`;
}

/** Push tags of the chats whose notifications this device muted. The switch is per chat; the device itself stays subscribed. */
export function mutedChatTags(): string[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(MUTED_KEY) || '[]');
    return Array.isArray(raw) ? raw.filter((t): t is string => typeof t === 'string') : [];
  } catch {
    return [];
  }
}

export function isChatMuted(chatId: string): boolean {
  return Boolean(chatId) && mutedChatTags().includes(chatPushTag(chatId));
}

export function setChatMuted(chatId: string, muted: boolean): void {
  if (!chatId) return;
  const tag = chatPushTag(chatId);
  const next = mutedChatTags().filter((t) => t !== tag);
  if (muted) next.push(tag);
  try {
    window.localStorage.setItem(MUTED_KEY, JSON.stringify(next.slice(-200)));
  } catch {
    /* ignore quota */
  }
}

/** Registers this device's push subscription and tells the server which chats it muted. Always enabled: muting one chat must not silence the others or the system alerts. */
export async function ensureWebPushSubscription(mutedTags: string[] = mutedChatTags()): Promise<boolean> {
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
      headers: { 'Content-Type': 'application/json', ...mutationHeaders('POST') },
      body: JSON.stringify({
        subscription: subscription.toJSON(),
        device_label: navigator.userAgent.slice(0, 120),
        enabled: true,
        muted_tags: mutedTags,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}