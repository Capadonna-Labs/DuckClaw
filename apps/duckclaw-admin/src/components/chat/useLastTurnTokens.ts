'use client';

import { useEffect } from 'react';
import { adminService } from '@/services/adminService';
import type { UsageTokenBreakdown } from '@/lib/formatTokenCount';
import type { ContextTokenBreakdown } from '@/lib/contextTokenBreakdown';
import { applyLastTurnTokenDisplay } from './adminChatPure';

/**
 * Context-window header: restore the last turn's tokens on open and after every
 * turn. Detached (iOS) turns finish from history and never see the done payload.
 */
export function useLastTurnTokens(opts: {
  enabled: boolean;
  chatId: string;
  loading: boolean;
  setLastTurnUsage: (v: UsageTokenBreakdown | null) => void;
  setContextEstimatedTokens: (v: number | null) => void;
  setContextTokenBreakdown: (v: ContextTokenBreakdown | null) => void;
}): void {
  const { enabled, chatId, loading, setLastTurnUsage, setContextEstimatedTokens, setContextTokenBreakdown } = opts;
  useEffect(() => {
    if (!enabled || !chatId || loading) return;
    let cancelled = false;
    void adminService
      .getPlaygroundChatActivity(chatId, 1)
      .then((a) => {
        if (cancelled || !a.last_turn_tokens) return;
        applyLastTurnTokenDisplay(
          setLastTurnUsage,
          setContextEstimatedTokens,
          a.last_turn_tokens,
          setContextTokenBreakdown
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enabled, chatId, loading, setLastTurnUsage, setContextEstimatedTokens, setContextTokenBreakdown]);
}
