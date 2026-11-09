'use client';

import { useCallback, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { ChatMsg } from '@/components/chat/types';

const QUOTE_MAX_CHARS = 1200;

/** Texto que viaja con el mensaje: la cita como blockquote markdown, recortada, seguida del mensaje. */
export function withQuote(quote: string, text: string): string {
  const q = quote.trim();
  if (!q) return text;
  const cut = q.length > QUOTE_MAX_CHARS ? `${q.slice(0, QUOTE_MAX_CHARS)}…` : q;
  return `${cut.split('\n').map((line) => `> ${line}`).join('\n')}\n\n${text}`;
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
