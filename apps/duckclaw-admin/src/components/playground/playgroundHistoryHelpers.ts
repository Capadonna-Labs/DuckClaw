import type { AdminConversation } from '@/services/adminService';
import { resolveWorkerDisplayName } from '@/lib/workerOptions';

import type { PlaygroundConfig } from './playgroundTypes';

export function formatConversationTime(iso: string): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso.slice(0, 16);
  const mins = Math.floor((Date.now() - t) / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `hace ${days}d`;
  return new Date(t).toLocaleDateString();
}
export function uniqueConversationsBySession(conversations: AdminConversation[]): AdminConversation[] {
  const seen = new Set<string>();
  return conversations.filter((conversation) => {
    if (seen.has(conversation.session_id)) return false;
    seen.add(conversation.session_id);
    return true;
  });
}

export function historyWorkerLabel(
  conversation: AdminConversation,
  workers?: NonNullable<PlaygroundConfig>['workers']
): string {
  const fromApi = (conversation.last_worker_display_name || '').trim();
  if (fromApi) return fromApi;
  const fromConfig = resolveWorkerDisplayName(workers, conversation.last_worker_id);
  if (fromConfig) return fromConfig;
  return conversation.last_worker_id?.trim() || 'sin worker';
}

