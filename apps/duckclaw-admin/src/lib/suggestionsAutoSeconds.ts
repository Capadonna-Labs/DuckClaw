/** Countdown (s) before suggestions Auto sends the recommended chip.
 * Source of truth is the chat's server state (returned with every /chat/suggestions); this module
 * mirrors it in localStorage and notifies every listener in the tab, so the chips and the Settings
 * field always show the same number. */

import { useEffect, useState } from 'react';

export const AUTO_SECONDS_DEFAULT = 15;
export const AUTO_SECONDS_MIN = 3;
export const AUTO_SECONDS_MAX = 300;
const KEY = 'duckclaw.chat.suggestionsAutoSeconds';
const EVT = 'duckclaw:suggestions-auto-seconds';

export function clampAutoSeconds(value: unknown): number {
  const n = Math.round(Number(value));
  if (!Number.isFinite(n)) return AUTO_SECONDS_DEFAULT;
  return Math.min(AUTO_SECONDS_MAX, Math.max(AUTO_SECONDS_MIN, n));
}

export function readAutoSeconds(): number {
  if (typeof window === 'undefined') return AUTO_SECONDS_DEFAULT;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? clampAutoSeconds(raw) : AUTO_SECONDS_DEFAULT;
  } catch {
    return AUTO_SECONDS_DEFAULT;
  }
}

export function writeAutoSeconds(value: unknown): number {
  const n = clampAutoSeconds(value);
  if (typeof window === 'undefined') return n;
  try {
    window.localStorage.setItem(KEY, String(n));
  } catch {
    /* private mode: still notify this tab */
  }
  window.dispatchEvent(new CustomEvent(EVT, { detail: n }));
  return n;
}

export function useAutoSeconds(): number {
  const [secs, setSecs] = useState(AUTO_SECONDS_DEFAULT);
  useEffect(() => {
    setSecs(readAutoSeconds());
    const onLocal = (e: Event) => setSecs(clampAutoSeconds((e as CustomEvent).detail));
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setSecs(readAutoSeconds());
    };
    window.addEventListener(EVT, onLocal);
    window.addEventListener('storage', onStorage);   // other tabs
    return () => {
      window.removeEventListener(EVT, onLocal);
      window.removeEventListener('storage', onStorage);
    };
  }, []);
  return secs;
}
