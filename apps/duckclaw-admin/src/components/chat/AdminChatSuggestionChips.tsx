'use client';

import { useEffect, useId, useState } from 'react';
import { ChevronDown, RefreshCw } from 'lucide-react';

type AdminChatSuggestionChipsProps = {
  suggestions: string[];
  onPick: (text: string) => void;
  /** Regenera sugerencias distintas (evitando las actuales). */
  onRefresh?: () => void | Promise<void>;
  refreshBusy?: boolean;
  /** Abierto por defecto al llegar sugerencias nuevas. */
  defaultOpen?: boolean;
};

/** Dropdown fijo "Sugerencias" encima del composer; las tarjetas persisten hasta el próximo turno. */
export function AdminChatSuggestionChips({
  suggestions,
  onPick,
  onRefresh,
  refreshBusy = false,
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
      <div className="flex items-center gap-0.5 px-2 py-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="min-w-0 flex-1 px-1 py-0.5 text-left"
          aria-expanded={open}
          aria-controls={panelId}
        >
          <span className="text-xs font-bold uppercase tracking-wider text-gov-gray-600 dark:text-dark-muted">
            Sugerencias
            <span className="ml-1.5 font-semibold normal-case text-gov-blue-700 dark:text-dark-cyan">
              ({suggestions.length})
            </span>
          </span>
        </button>
        {onRefresh ? (
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={refreshBusy}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gov-blue-700 hover:bg-gov-blue-50 disabled:opacity-50 dark:text-dark-cyan dark:hover:bg-dark-bg"
            aria-label="Regenerar sugerencias"
            title="Regenerar sugerencias"
          >
            <RefreshCw size={14} className={refreshBusy ? 'animate-spin' : ''} aria-hidden />
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gov-gray-500 hover:bg-gov-gray-100 dark:text-dark-muted dark:hover:bg-dark-bg"
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
          className="flex flex-wrap gap-1.5 border-t border-gov-gray-100 px-3 py-2 dark:border-dark-border"
        >
          {suggestions.map((s, i) => (
            <button
              key={`${i}:${s}`}
              type="button"
              role="listitem"
              onClick={() => onPick(s)}
              className="rounded-full border border-gov-gray-200 bg-gov-gray-50 px-3 py-1.5 text-left text-xs text-gov-gray-700 hover:border-gov-blue-200 hover:bg-gov-blue-50 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text dark:hover:bg-dark-surface"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
