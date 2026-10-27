'use client';

import { useCallback, useEffect, useRef, useState, type PointerEvent, type RefObject } from 'react';

const MIN_THUMB = 36;

/**
 * Vertical scroll slider drawn by us on the right edge of the chat list: iOS hides the native
 * bar of that list under the glass header/composer, so it is rendered (and draggable) here.
 * `className` places the rail between the overlays (same offsets as the list's padding).
 */
export function ChatScrollRail({ scrollRef, className = '' }: { scrollRef: RefObject<HTMLDivElement>; className?: string }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState({ h: 0, top: 0, show: false });
  const drag = useRef<{ y: number; scroll: number } | null>(null);

  const measure = useCallback(() => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!el || !track) return;
    const room = el.scrollHeight - el.clientHeight;
    const trackH = track.clientHeight;
    if (room <= 1 || trackH <= 0) {
      setThumb((t) => (t.show ? { h: 0, top: 0, show: false } : t));
      return;
    }
    const h = Math.min(trackH, Math.max(MIN_THUMB, (trackH * el.clientHeight) / el.scrollHeight));
    setThumb({ h, top: (el.scrollTop / room) * (trackH - h), show: true });
  }, [scrollRef]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    const mo = new MutationObserver(measure);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    window.addEventListener('resize', measure);
    return () => {
      el.removeEventListener('scroll', measure);
      ro.disconnect();
      mo.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [scrollRef, measure]);

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    if (!el) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { y: e.clientY, scroll: el.scrollTop };
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!drag.current || !el || !track) return;
    const travel = track.clientHeight - thumb.h;
    if (travel <= 0) return;
    el.scrollTop = drag.current.scroll + ((e.clientY - drag.current.y) * (el.scrollHeight - el.clientHeight)) / travel;
  };
  const onUp = () => {
    drag.current = null;
  };
  // A tap on the track (not the thumb) jumps there: the tapped point becomes the thumb's centre.
  const onTrack = (e: PointerEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!el || !track || e.target !== e.currentTarget) return;
    const rect = track.getBoundingClientRect();
    const travel = rect.height - thumb.h;
    if (travel <= 0) return;
    const ratio = Math.min(1, Math.max(0, (e.clientY - rect.top - thumb.h / 2) / travel));
    el.scrollTop = ratio * (el.scrollHeight - el.clientHeight);
  };

  return (
    <div
      ref={trackRef}
      onPointerDown={onTrack}
      aria-hidden
      className={`absolute right-0.5 z-[5] w-2.5 rounded-full bg-gov-gray-300/40 dark:bg-white/10 ${thumb.show ? '' : 'hidden'} ${className}`}
    >
      <div
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        style={{ height: thumb.h, transform: `translateY(${thumb.top}px)`, touchAction: 'none' }}
        className="w-full cursor-grab rounded-full bg-gov-gray-400 active:cursor-grabbing dark:bg-slate-400"
      />
    </div>
  );
}
