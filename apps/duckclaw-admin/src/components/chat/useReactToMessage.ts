'use client';

import { useCallback, type Dispatch, type SetStateAction } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatMsg, ChatReaction } from '@/components/chat/types';

/** The user's reaction after tapping `emoji`: the same one again removes it, another replaces it. */
export function nextUserReaction(reactions: ChatReaction[] | undefined, emoji: string): string | null {
  return reactions?.some((r) => r.by === 'user' && r.emoji === emoji) ? null : emoji;
}

export function withUserReaction(reactions: ChatReaction[] | undefined, emoji: string | null): ChatReaction[] {
  const rest = (reactions ?? []).filter((r) => r.by !== 'user');
  return emoji ? [{ emoji, by: 'user' }, ...rest] : rest;
}

/** Who reacted with what, grouped by emoji; the user's own come first. */
export function groupReactions(reactions: ChatReaction[] | undefined): { emoji: string; mine: boolean; agent: boolean }[] {
  const by = new Map<string, { emoji: string; mine: boolean; agent: boolean }>();
  for (const r of reactions ?? []) {
    const g = by.get(r.emoji) ?? { emoji: r.emoji, mine: false, agent: false };
    if (r.by === 'user') g.mine = true;
    else g.agent = true;
    by.set(r.emoji, g);
  }
  return [...by.values()].sort((a, b) => Number(b.mine) - Number(a.mine));
}

/** React to a message (optimistic; the gateway keeps it and the agent reads it on its next turn). Undone if the call fails. */
export function useReactToMessage(
  messages: ChatMsg[],
  setMessages: Dispatch<SetStateAction<ChatMsg[]>>,
  chatId: string,
  tenantId?: string
) {
  return useCallback(
    (index: number, emoji: string) => {
      const m = messages[index];
      if (!m || (m.role !== 'user' && m.role !== 'assistant')) return;
      const before = m.reactions;
      const next = nextUserReaction(before, emoji);
      const apply = (reactions: ChatReaction[] | undefined) =>
        setMessages((all) => all.map((x, i) => (i === index ? { ...x, reactions } : x)));
      apply(withUserReaction(before, next));
      adminService
        .reactToMessage(chatId, { role: m.role, text: m.storedText ?? m.text, emoji: next }, tenantId)
        .catch(() => apply(before));
    },
    [messages, setMessages, chatId, tenantId]
  );
}
