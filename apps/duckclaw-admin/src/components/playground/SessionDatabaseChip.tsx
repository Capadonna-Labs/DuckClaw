'use client';

import { Database } from 'lucide-react';
import { sessionDbScopeLabel, shortenSessionDbPath } from '@/lib/sessionDbPath';

type SessionDatabaseChipProps = {
  path: string;
  scope?: string;
  onConfigure?: () => void;
};

/** Pill compacto para la barra de composición del chat. */
export function SessionDatabaseChip({ path, scope, onConfigure }: SessionDatabaseChipProps) {
  const hasPath = Boolean((path || '').trim());
  const short = shortenSessionDbPath(path);

  if (!hasPath) {
    return (
      <button
        type="button"
        onClick={onConfigure}
        className="inline-flex max-w-full items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-bold text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
      >
        <Database size={11} aria-hidden />
        <span className="truncate">BD sin resolver</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onConfigure}
      title={`${path}\n${sessionDbScopeLabel(scope)}`}
      className="inline-flex max-w-[min(100%,14rem)] items-center gap-1 rounded-full border border-gov-blue-200 bg-white px-2 py-1 text-[10px] font-semibold text-gov-blue-900 hover:bg-gov-blue-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan dark:hover:bg-dark-bg"
    >
      <Database size={11} aria-hidden className="shrink-0" />
      <span className="truncate font-mono">{short}</span>
    </button>
  );
}
