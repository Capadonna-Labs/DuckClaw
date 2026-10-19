'use client';

import { useCallback, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { ChatMsg } from '@/components/chat/types';

/** Cita un mensaje en el input (deslizar a la derecha) para preguntar sobre él. */
export function useQuoteMessage(
  messages: ChatMsg[],
  setInput: Dispatch<SetStateAction<string>>,
  inputRef: RefObject<HTMLTextAreaElement | null>
) {
  return useCallback(
    (messageIndex: number) => {
      const text = (messages[messageIndex]?.text || '').trim();
      if (!text) return;
      const quoted = text.split('\n').map((line) => `> ${line}`).join('\n');
      setInput((prev) => `${quoted}\n\n${prev}`);
      window.requestAnimationFrame(() => {
        const el = inputRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      });
    },
    [messages, setInput, inputRef]
  );
}
