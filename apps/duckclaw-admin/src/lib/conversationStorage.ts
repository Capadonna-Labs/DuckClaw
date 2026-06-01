/** Conversación admin activa (compartida Playground + burbuja). */

const ACTIVE_CONV_KEY = 'duckclaw-admin-active-conv';

function activeConversationKey(tenantId?: string): string {
  const tid = (tenantId || '').trim();
  return tid ? `${ACTIVE_CONV_KEY}:${tid}` : ACTIVE_CONV_KEY;
}

export function readActiveConversationId(tenantId?: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = localStorage.getItem(activeConversationKey(tenantId));
    if (v?.trim()) return v.trim();
    if (tenantId) {
      return localStorage.getItem(ACTIVE_CONV_KEY)?.trim() || null;
    }
    return v?.trim() || null;
  } catch {
    return null;
  }
}

export function writeActiveConversationId(sessionId: string | null, tenantId?: string): void {
  if (typeof window === 'undefined') return;
  try {
    const key = activeConversationKey(tenantId);
    if (sessionId?.trim()) {
      localStorage.setItem(key, sessionId.trim());
    } else {
      localStorage.removeItem(key);
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
