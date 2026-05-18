'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const BOTTOM_THRESHOLD_PX = 72;

export type UseChatScrollAnchorOptions = {
  /** Fuerza scroll al fondo al cambiar (p. ej. sessionId). */
  resetKey?: string;
  loading?: boolean;
  thinking?: boolean;
};

export function useChatScrollAnchor(
  /** Cambia cuando hay mensajes nuevos o el último mensaje crece (streaming). */
  contentKey: string,
  options?: UseChatScrollAnchorOptions
) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const loading = options?.loading ?? false;
  const thinking = options?.thinking ?? false;

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    pinnedToBottomRef.current = true;
    setShowScrollButton(false);
  }, []);

  const onScroll = useCallback(() => {
    const near = isNearBottom();
    pinnedToBottomRef.current = near;
    setShowScrollButton(!near);
  }, [isNearBottom]);

  useEffect(() => {
    pinnedToBottomRef.current = true;
    setShowScrollButton(false);
    requestAnimationFrame(() => scrollToBottom('auto'));
  }, [options?.resetKey, scrollToBottom]);

  useEffect(() => {
    if (!pinnedToBottomRef.current) return;
    const behavior: ScrollBehavior = loading || thinking ? 'smooth' : 'auto';
    requestAnimationFrame(() => scrollToBottom(behavior));
  }, [contentKey, loading, thinking, scrollToBottom]);

  return {
    scrollRef,
    showScrollButton,
    scrollToBottom,
    onScroll,
  };
}
