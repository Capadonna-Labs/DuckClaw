'use client';

import { useEffect, useRef, useState } from 'react';
import { writeAutoSeconds } from '@/lib/suggestionsAutoSeconds';
import { adminService } from '@/services/adminService';
import type { ChatMsg } from '@/components/chat/types';
import { lastUserAssistantExchange, suggestionsExchangeKey } from './adminChatPure';

type Args = {
  enabled: boolean;
  suggestionsEnabled: boolean;
  chatId: string;
  loading: boolean;
  thinking: boolean;
  historyLoading: boolean;
  messages: ChatMsg[];
  tenantId?: string;
  vaultPath: string;
};

/** Reply chips for the last user→assistant exchange (state, reset per chat, fetch). */
export function useChatSuggestions({
  enabled,
  suggestionsEnabled,
  chatId,
  loading,
  thinking,
  historyLoading,
  messages,
  tenantId,
  vaultPath,
}: Args) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [recommendedSuggestionIndex, setRecommendedSuggestionIndex] = useState(0);
  const [suggestionsAutoEnabled, setSuggestionsAutoEnabled] = useState<boolean | null>(null);
  const suggestionsExchangeKeyRef = useRef('');
  /** Exchange whose chips are wanted now / being fetched (generation takes ~15 s). */
  const suggestionsWantedKeyRef = useRef('');
  const suggestionsInFlightKeyRef = useRef('');

  useEffect(() => {
    setSuggestions([]);
    setRecommendedSuggestionIndex(0);
    setSuggestionsAutoEnabled(null);
    suggestionsExchangeKeyRef.current = '';
    suggestionsWantedKeyRef.current = '';
    suggestionsInFlightKeyRef.current = '';
  }, [chatId]);

  /**
   * Regenerar chips cuando cambia el último intercambio user→assistant
   * (abrir chat, reload de historial, o turno que no actualizó la ref).
   * La clave evita refetch duplicado tras un turno live que ya regeneró.
   */
  useEffect(() => {
    if (!suggestionsEnabled) {
      setSuggestions([]);
      setRecommendedSuggestionIndex(0);
      suggestionsExchangeKeyRef.current = '';
      return;
    }
    if (loading || thinking) {
      // A new turn clears chips; a late answer for the old exchange must not refill them.
      suggestionsWantedKeyRef.current = '';
      return;
    }
    if (!enabled || !chatId || historyLoading) return;
    const exchange = lastUserAssistantExchange(messages);
    if (!exchange) return;
    const key = suggestionsExchangeKey(chatId, exchange.userText, exchange.assistantText);
    suggestionsWantedKeyRef.current = key;
    // No effect cleanup cancel: `messages` changes (history polling, heartbeats) kept
    // aborting the ~15 s generation, so chips never landed. Key refs dedupe instead.
    if (suggestionsExchangeKeyRef.current === key || suggestionsInFlightKeyRef.current === key) return;
    suggestionsInFlightKeyRef.current = key;
    const stale = () => suggestionsWantedKeyRef.current !== key;
    void adminService
      .getChatSuggestions({
        chat_id: chatId,
        tenant_id: tenantId,
        last_user_message: exchange.userText.slice(0, 8000),
        last_assistant_message: exchange.assistantText.slice(0, 16000),
        vault_db_path: vaultPath || undefined,
      })
      .then((r) => {
        if (suggestionsInFlightKeyRef.current === key) suggestionsInFlightKeyRef.current = '';
        if (stale()) return;
        const next = (r.suggestions ?? []).map((s) => s.trim()).filter(Boolean);
        setSuggestions(next);
        const rawIdx = Number(r.recommended_index ?? 0);
        const idx =
          next.length === 0
            ? 0
            : Number.isFinite(rawIdx)
              ? Math.min(Math.max(0, Math.floor(rawIdx)), next.length - 1)
              : 0;
        setRecommendedSuggestionIndex(idx);
        if (typeof r.suggestions_auto_enabled === 'boolean') {
          setSuggestionsAutoEnabled(r.suggestions_auto_enabled);
        }
        if (typeof r.suggestions_auto_seconds === 'number') writeAutoSeconds(r.suggestions_auto_seconds);
        // Only lock the exchange after a successful apply, so an empty answer can refetch.
        suggestionsExchangeKeyRef.current = next.length > 0 ? key : '';
      })
      .catch(() => {
        if (suggestionsInFlightKeyRef.current === key) suggestionsInFlightKeyRef.current = '';
        if (stale()) return;
        // Transient BFF timeout after a long turn — retry next effect cycle.
        suggestionsExchangeKeyRef.current = '';
      });
  }, [enabled, suggestionsEnabled, chatId, loading, historyLoading, thinking, messages, tenantId, vaultPath]);

  return {
    suggestions,
    setSuggestions,
    recommendedSuggestionIndex,
    setRecommendedSuggestionIndex,
    suggestionsAutoEnabled,
    setSuggestionsAutoEnabled,
    suggestionsExchangeKeyRef,
  };
}
