'use client';

import { matchingSlashCommands } from '@/components/chat/adminChatPure';

/** Menú "/" fijo encima del composer — mismo hueco visual que AdminChatSuggestionChips. */
export function SlashCommandMenu({
  input,
  onPick,
  extraCommands = [],
}: {
  input: string;
  onPick: (cmd: string) => void;
  /** Directive skills instalados (catálogo global) que se muestran junto a los genéricos. */
  extraCommands?: { cmd: string; description: string }[];
}) {
  const matches = matchingSlashCommands(input, extraCommands);
  if (matches.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-xl border border-gov-gray-200 bg-white/90 shadow-sm dark:border-dark-border dark:bg-dark-surface/90">
      <ul role="listbox" className="divide-y divide-gov-gray-100 dark:divide-dark-border">
        {matches.map((c) => (
          <li key={c.cmd}>
            <button
              type="button"
              onClick={() => onPick(c.cmd)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-gov-gray-50 dark:hover:bg-dark-bg"
            >
              <span className="shrink-0 font-mono text-sm font-semibold text-gov-blue-700 dark:text-dark-cyan">
                {c.cmd}
              </span>
              <span className="truncate text-xs text-gov-gray-500 dark:text-dark-muted">
                {c.description}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
