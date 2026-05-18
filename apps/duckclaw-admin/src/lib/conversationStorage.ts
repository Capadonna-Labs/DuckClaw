/** Conversación admin activa (compartida Playground + burbuja). */

const ACTIVE_CONV_KEY = 'duckclaw-admin-active-conv';

export function readActiveConversationId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = localStorage.getItem(ACTIVE_CONV_KEY);
    return v?.trim() || null;
  } catch {
    return null;
  }
}

export function writeActiveConversationId(sessionId: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (sessionId?.trim()) {
      localStorage.setItem(ACTIVE_CONV_KEY, sessionId.trim());
    } else {
      localStorage.removeItem(ACTIVE_CONV_KEY);
    }
  } catch {
    /* ignore quota */
  }
}

/** Sección admin para metadatos (filtro inbox). */
export function sectionFromPath(pathname: string): string {
  const slug = pathname.replace(/^\/+|\/+$/g, '').replace(/\//g, '-') || 'root';
  if (!slug || slug === 'root') return 'root';
  if (slug === 'playground' || slug.startsWith('playground')) return 'playground';
  if (slug.startsWith('kanban')) return 'kanban';
  if (slug.startsWith('vnc')) return 'vnc';
  if (slug.startsWith('train')) return 'train';
  if (slug.startsWith('admin-')) {
    const rest = slug.slice('admin-'.length);
    return rest.split('-')[0] || 'admin';
  }
  return slug.split('-')[0] || 'other';
}
