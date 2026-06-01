'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { readActiveConversationId, writeActiveConversationId } from '@/lib/conversationStorage';

export function useActiveConversation(tenantId: string | undefined, section: string) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [bootstrapping, setBootstrapping] = useState(true);

  const bumpRefresh = useCallback(() => setRefreshToken((t) => t + 1), []);

  const syncConversationTitle = useCallback((title: string) => {
    setConversationTitle(title);
  }, []);

  const renameConversation = useCallback(
    async (title: string) => {
      if (!sessionId) return;
      const tid = tenantId || 'default';
      const meta = await adminService.patchConversation(sessionId, title, tid);
      setConversationTitle(meta.title || title);
      bumpRefresh();
    },
    [sessionId, tenantId, bumpRefresh]
  );

  const selectConversation = useCallback((id: string, title?: string) => {
    const tid = tenantId || 'default';
    writeActiveConversationId(id, tid);
    setSessionId(id);
    setConversationTitle(title ?? null);
  }, [tenantId]);

  const createConversation = useCallback(async () => {
    const tid = tenantId || 'default';
    const created = await adminService.createConversation({ section }, tid);
    selectConversation(created.session_id, created.title);
    bumpRefresh();
    return created;
  }, [tenantId, section, selectConversation, bumpRefresh]);

  const selectConversationById = useCallback(async (id: string) => {
    const tid = tenantId || 'default';
    const meta = await adminService.getConversation(id, tid);
    selectConversation(meta.session_id, meta.title);
    bumpRefresh();
    return meta;
  }, [tenantId, selectConversation, bumpRefresh]);

  useEffect(() => {
    let cancelled = false;
    const tid = tenantId || 'default';

    async function bootstrap() {
      setBootstrapping(true);
      const stored = readActiveConversationId(tid);
      if (stored) {
        try {
          const meta = await adminService.getConversation(stored, tid);
          if (!cancelled) {
            setSessionId(stored);
            setConversationTitle(meta.title || null);
            setBootstrapping(false);
          }
          return;
        } catch {
          writeActiveConversationId(null, tid);
        }
      }
      try {
        const listed = await adminService.listConversations({ tenant_id: tid, limit: 1 });
        if (cancelled) return;
        const first = listed.conversations?.[0];
        if (first) {
          selectConversation(first.session_id, first.title);
          setBootstrapping(false);
          return;
        }
        const created = await adminService.createConversation({ section }, tid);
        if (cancelled) return;
        selectConversation(created.session_id, created.title);
      } catch {
        if (!cancelled) setSessionId(null);
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [tenantId, section, selectConversation]);

  return {
    sessionId,
    conversationTitle,
    selectConversation,
    createConversation,
    selectConversationById,
    syncConversationTitle,
    renameConversation,
    refreshToken,
    bumpRefresh,
    bootstrapping,
  };
}
