'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

export const SUGGESTIONS_AUTO_STORAGE_KEY = 'duckclaw.chat.suggestionsAuto';
export const SUGGESTIONS_AUTO_COUNTDOWN_SEC = 15;

type AdminChatSuggestionChipsProps = {
  suggestions: string[];
  onPick: (text: string) => void;
  /** Abierto por defecto al llegar sugerencias nuevas. */
  defaultOpen?: boolean;
  /** Índice (0-based) de la sugerencia recomendada por el modelo. */
  recommendedIndex?: number;
  /** True mientras el chat está enviando (pausa el countdown). */
  busy?: boolean;
  /**
   * Preferencia persistida en vault (agente / API).
   * `false` fuerza Auto off; `true` fuerza Auto on; `null`/omit → localStorage.
   */
  serverAutoEnabled?: boolean | null;
  /** Persistir toggle del usuario (limpia suppress del agente al activar). */
  onAutoChange?: (enabled: boolean) => void;
};

function readStoredAuto(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(SUGGESTIONS_AUTO_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeStoredAuto(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SUGGESTIONS_AUTO_STORAGE_KEY, enabled ? '1' : '0');
  } catch {
    /* ignore quota */
  }
}

/** Dropdown fijo "Sugerencias" encima del composer; Auto on/off en el header. */
export function AdminChatSuggestionChips({
  suggestions,
  onPick,
  defaultOpen = true,
  recommendedIndex = 0,
  busy = false,
  serverAutoEnabled = null,
  onAutoChange,
}: AdminChatSuggestionChipsProps) {
  const panelId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const [autoEnabled, setAutoEnabled] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const cancelledRef = useRef(false);
  const tickRef = useRef<number | null>(null);
  const onPickRef = useRef(onPick);
  const signature = suggestions.join('\0');
  const safeRecommended =
    suggestions.length === 0
      ? 0
      : Math.min(Math.max(0, Math.floor(recommendedIndex)), suggestions.length - 1);

  const clearTick = () => {
    if (tickRef.current != null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  };

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    if (serverAutoEnabled === false) {
      setAutoEnabled(false);
      writeStoredAuto(false);
      cancelledRef.current = true;
      clearTick();
      setCountdown(null);
      return;
    }
    if (serverAutoEnabled === true) {
      setAutoEnabled(true);
      writeStoredAuto(true);
      return;
    }
    setAutoEnabled(readStoredAuto());
  }, [serverAutoEnabled]);

  useEffect(() => {
    if (suggestions.length === 0) return;
    setOpen(defaultOpen);
  }, [signature, defaultOpen, suggestions.length]);

  useEffect(() => {
    cancelledRef.current = false;
    clearTick();
    setCountdown(null);
    if (!autoEnabled || busy || suggestions.length === 0) return;

    let remaining = SUGGESTIONS_AUTO_COUNTDOWN_SEC;
    setCountdown(remaining);
    tickRef.current = window.setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearTick();
        setCountdown(null);
        if (!cancelledRef.current) {
          const text = (suggestions[safeRecommended] || '').trim();
          if (text) onPickRef.current(text);
        }
        return;
      }
      if (cancelledRef.current) return;
      setCountdown(remaining);
    }, 1000);

    return () => {
      clearTick();
    };
  }, [autoEnabled, busy, signature, safeRecommended, suggestions]);

  if (suggestions.length === 0) return null;

  const setAuto = (next: boolean) => {
    cancelledRef.current = true;
    clearTick();
    setCountdown(null);
    setAutoEnabled(next);
    writeStoredAuto(next);
    onAutoChange?.(next);
  };

  /** Stop this turn's countdown only — Auto stays on for the next suggestion set. */
  const cancelCountdown = () => {
    cancelledRef.current = true;
    clearTick();
    setCountdown(null);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm dark:border-dark-border dark:bg-dark-surface/90">
      {/* Auto sits immediately beside the label (not far-right); chevron keeps expand affordance. */}
      <div className="flex w-full items-center gap-2 px-3 py-2">
        <span className="min-w-0 shrink-0 text-xs font-bold uppercase tracking-wider text-gov-gray-600 dark:text-dark-muted">
          Sugerencias
          <span className="ml-1.5 font-semibold normal-case text-gov-blue-700 dark:text-dark-cyan">
            ({suggestions.length})
          </span>
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={autoEnabled}
          aria-label="Modo auto de sugerencias"
          onClick={() => setAuto(!autoEnabled)}
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide transition-colors ${
            autoEnabled
              ? 'border-gov-blue-500 bg-gov-blue-600 text-white dark:border-dark-cyan dark:bg-dark-cyan dark:text-dark-bg'
              : 'border-gov-gray-200 bg-gov-gray-50 text-gov-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted'
          }`}
        >
          Auto {autoEnabled ? 'on' : 'off'}
        </button>
        {autoEnabled && countdown != null ? (
          <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-gov-blue-600 dark:text-dark-cyan">
            {countdown}s
          </span>
        ) : null}
        {autoEnabled && countdown != null ? (
          <button
            type="button"
            onClick={cancelCountdown}
            className="shrink-0 rounded-full border border-gov-gray-200 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-gov-gray-500 hover:bg-gov-gray-50 dark:border-dark-border dark:text-dark-muted dark:hover:bg-dark-bg"
            aria-label="Cancelar auto de este turno"
          >
            Cancelar
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto flex shrink-0 items-center justify-center rounded-md p-1 text-gov-gray-500 hover:bg-gov-gray-100 dark:text-dark-muted dark:hover:bg-dark-bg"
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={open ? 'Ocultar sugerencias' : 'Mostrar sugerencias'}
        >
          <ChevronDown
            size={16}
            className={`transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
            aria-hidden
          />
        </button>
      </div>
      {open ? (
        <div
          id={panelId}
          role="list"
          className="flex flex-wrap items-center gap-1.5 border-t border-gov-gray-100 px-3 py-2 dark:border-dark-border"
        >
          {suggestions.map((s, i) => {
            const recommended = i === safeRecommended;
            return (
              <button
                key={`${i}:${s}`}
                type="button"
                role="listitem"
                onClick={() => {
                  cancelCountdown();
                  onPick(s);
                }}
                className={`rounded-full border px-3 py-1.5 text-left text-xs transition-colors ${
                  recommended && autoEnabled
                    ? 'border-gov-blue-400 bg-gov-blue-50 text-gov-blue-900 ring-1 ring-gov-blue-200 dark:border-dark-cyan dark:bg-dark-bg dark:text-dark-text dark:ring-dark-cyan/40'
                    : 'border-gov-gray-200 bg-gov-gray-50 text-gov-gray-700 hover:bg-gov-blue-50 hover:border-gov-blue-200 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text dark:hover:bg-dark-surface'
                }`}
              >
                {recommended && autoEnabled ? (
                  <span className="mr-1 text-[10px] font-bold uppercase tracking-wide text-gov-blue-700 dark:text-dark-cyan">
                    Mejor
                  </span>
                ) : null}
                {s}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
