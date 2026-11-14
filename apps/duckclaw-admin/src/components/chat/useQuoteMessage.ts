'use client';

import { useCallback, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { ChatMsg } from '@/components/chat/types';

const QUOTE_MAX_CHARS = 140;

/** Texto que viaja con el mensaje: solo el comienzo de lo citado, en una línea (el agente ya tiene el historial; reenviarlo entero lo duplicaba), seguido del mensaje. */
export function withQuote(quote: string, text: string): string {
  const q = quotePreview(quote);
  if (!q) return text;
  const cut = q.length > QUOTE_MAX_CHARS ? `${q.slice(0, QUOTE_MAX_CHARS).trimEnd()}…` : q;
  return `> ${cut}\n\n${text}`;
}

/** Una línea para el chip del compositor: sin markdown pesado, el resto lo recorta el CSS. */
export function quotePreview(quote: string): string {
  return quote.replace(/[#*_`>|]+/g, ' ').replace(/\s+/g, ' ').trim();
}

/** Responder a un mensaje (deslizar a la derecha): lo guarda como cita pendiente, no lo pega en el input. */
export function useQuoteMessage(
  messages: ChatMsg[],
  setQuote: Dispatch<SetStateAction<string>>,
  inputRef: RefObject<HTMLTextAreaElement | null>
) {
  return useCallback(
    (messageIndex: number) => {
      const text = (messages[messageIndex]?.text || '').trim();
      if (!text) return;
      setQuote(text);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    },
    [messages, setQuote, inputRef]
  );
}
