'use client';

import { useEffect, useRef } from 'react';
import type { ChatReaction } from '@/components/chat/types';
import { groupReactions } from '@/components/chat/useReactToMessage';

export const REACTION_EMOJIS = ['👍', '👎', '❤️', '😂', '🎉', '😮', '🔥', '👀', '🙏', '😢', '💯'] as const;

/** The emoji bar that opens on long-press or from the smiley button; a tap on the emoji already chosen removes it. */
export function ReactionPicker({
  current,
  onPick,
  onClose,
  alignRight,
}: {
  current: string | undefined;
  onPick: (emoji: string) => void;
  onClose: () => void;
  alignRight: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const away = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('pointerdown', away);
    return () => document.removeEventListener('pointerdown', away);
  }, [onClose]);
  return (
    <div
      ref={ref}
      role="menu"
      aria-label="Reaccionar al mensaje"
      className={`absolute -top-11 z-20 flex max-w-[92vw] gap-0.5 overflow-x-auto rounded-full border border-gov-gray-200 bg-white px-1.5 py-1 shadow-lg dark:border-dark-border dark:bg-dark-surface ${
        alignRight ? 'right-2' : 'left-2'
      }`}
    >
      {REACTION_EMOJIS.map((e) => (
        <button
          key={e}
          type="button"
          role="menuitem"
          onClick={() => {
            onPick(e);
            onClose();
          }}
          className={`size-8 shrink-0 rounded-full text-lg leading-none transition-transform hover:scale-125 ${
            current === e ? 'bg-gov-blue-100 dark:bg-gov-blue-900/40' : ''
          }`}
          aria-label={`Reaccionar con ${e}`}
        >
          {e}
        </button>
      ))}
    </div>
  );
}

/** Small chips under a message: the user's reaction (tap to remove) and the agent's. */
export function ReactionChips({
  reactions,
  onToggle,
  alignRight,
}: {
  reactions: ChatReaction[] | undefined;
  onToggle?: (emoji: string) => void;
  alignRight: boolean;
}) {
  const groups = groupReactions(reactions);
  if (!groups.length) return null;
  return (
    <div className={`mt-1 flex flex-wrap gap-1 px-1 ${alignRight ? 'justify-end' : ''}`}>
      {groups.map((g) => (
        <button
          key={g.emoji}
          type="button"
          disabled={!g.mine || !onToggle}
          onClick={() => g.mine && onToggle?.(g.emoji)}
          title={g.mine && g.agent ? 'Tú y el agente' : g.mine ? 'Tu reacción (toca para quitarla)' : 'Reacción del agente'}
          className={`inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-sm leading-none ${
            g.mine
              ? 'border-gov-blue-300 bg-gov-blue-50 dark:border-gov-blue-700 dark:bg-gov-blue-900/30'
              : 'border-gov-gray-200 bg-gov-gray-50 dark:border-dark-border dark:bg-dark-bg'
          }`}
        >
          <span>{g.emoji}</span>
          {g.agent ? <span className="text-[10px] font-semibold text-gov-gray-500 dark:text-dark-muted">IA</span> : null}
        </button>
      ))}
    </div>
  );
}
