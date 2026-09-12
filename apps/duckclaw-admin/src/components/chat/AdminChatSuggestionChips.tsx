'use client';

import { useEffect, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';

type AdminChatSuggestionChipsProps = {
  suggestions: string[];
  onPick: (text: string) => void;
  /** Abierto por defecto al llegar sugerencias nuevas. */
  defaultOpen?: boolean;
};

/** Dropdown fijo "Sugerencias" encima del composer; las tarjetas persisten hasta el próximo turno. */
export function AdminChatSuggestionChips({
  suggestions,
  onPick,
  defaultOpen = true,
}: AdminChatSuggestionChipsProps) {
  const panelId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const signature = suggestions.join('\0');

  useEffect(() => {
    if (suggestions.length === 0) return;
    setOpen(defaultOpen);
  }, [signature, defaultOpen, suggestions.length]);

  if (suggestions.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm dark:border-dark-border dark:bg-dark-surface/90">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        aria-expanded={open}
        aria-controls={panelId}
      >
        <span className="text-xs font-bold uppercase tracking-wider text-gov-gray-600 dark:text-dark-muted">
          Sugerencias
          <span className="ml-1.5 font-semibold normal-case text-gov-blue-700 dark:text-dark-cyan">
            ({suggestions.length})
          </span>
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-gov-gray-500 transition-transform dark:text-dark-muted ${
            open ? 'rotate-0' : '-rotate-90'
          }`}
          aria-hidden
        />
      </button>
      {open ? (
        <div
          id={panelId}
          role="list"
          className="flex flex-wrap gap-1.5 border-t border-gov-gray-100 px-3 py-2 dark:border-dark-border"
        >
          {suggestions.map((s, i) => (
            <button
              key={`${i}:${s}`}
              type="button"
              role="listitem"
              onClick={() => onPick(s)}
              className="rounded-full border border-gov-gray-200 bg-gov-gray-50 px-3 py-1.5 text-left text-xs text-gov-gray-700 hover:bg-gov-blue-50 hover:border-gov-blue-200 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text dark:hover:bg-dark-surface"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
