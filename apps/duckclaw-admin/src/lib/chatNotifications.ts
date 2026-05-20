export type ChatNotificationPayload = {
  title: string;
  body: string;
  tag?: string;
  onClick?: () => void;
};

export function notificationsSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window;
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  if (!notificationsSupported()) return 'unsupported';
  return Notification.permission;
}

export async function requestNotificationPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (!notificationsSupported()) return 'unsupported';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

/** Pestaña o ventana no visible para el usuario (incl. otra app encima). */
export function isDocumentInBackground(): boolean {
  if (typeof document === 'undefined') return false;
  return document.visibilityState === 'hidden';
}

export function shouldNotifyInBackground(): boolean {
  if (typeof document === 'undefined') return false;
  return isDocumentInBackground() || !document.hasFocus();
}

/** Panel abierto pero el usuario cambió de pestaña — no contar como «visto». */
export function isChatPanelActivelyViewed(panelOpen: boolean): boolean {
  if (!panelOpen) return false;
  if (typeof document === 'undefined') return true;
  return document.visibilityState === 'visible' && document.hasFocus();
}

export function showChatNotification(
  payload: ChatNotificationPayload,
  options?: { requireBackground?: boolean }
): boolean {
  if (!notificationsSupported() || Notification.permission !== 'granted') return false;
  const requireBackground = options?.requireBackground !== false;
  if (requireBackground && !shouldNotifyInBackground()) return false;

  try {
    const n = new Notification(payload.title, {
      body: payload.body,
      tag: payload.tag,
      icon: '/favicon.ico',
    });
    n.onclick = () => {
      window.focus();
      payload.onClick?.();
      n.close();
    };
    return true;
  } catch {
    return false;
  }
}

export function snippetFromMessage(text: string, maxLen = 120): string {
  const oneLine = text.replace(/\s+/g, ' ').trim();
  if (!oneLine) return 'Nuevo mensaje del asistente';
  if (oneLine.length <= maxLen) return oneLine;
  return `${oneLine.slice(0, maxLen - 1)}…`;
}
