'use client';

import { useCallback, useEffect, useState } from 'react';

const EDGE_THRESHOLD_PX = 120;

export function useScrollFabPair(scrollEl: HTMLElement | null) {
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  const onScroll = useCallback(() => {
    if (!scrollEl) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollEl;
    setShowScrollTop(scrollTop > EDGE_THRESHOLD_PX);
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight > EDGE_THRESHOLD_PX);
  }, [scrollEl]);

  useEffect(() => {
    if (!scrollEl) return;
    onScroll();
    scrollEl.addEventListener('scroll', onScroll, { passive: true });
    const ro = new ResizeObserver(onScroll);
    ro.observe(scrollEl);
    return () => {
      scrollEl.removeEventListener('scroll', onScroll);
      ro.disconnect();
    };
  }, [scrollEl, onScroll]);

  const scrollToTop = useCallback(
    (behavior: ScrollBehavior = 'smooth') => {
      scrollEl?.scrollTo({ top: 0, behavior });
    },
    [scrollEl]
  );

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = 'smooth') => {
      if (!scrollEl) return;
      scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior });
    },
    [scrollEl]
  );

  return { showScrollTop, showScrollBottom, scrollToTop, scrollToBottom };
}
