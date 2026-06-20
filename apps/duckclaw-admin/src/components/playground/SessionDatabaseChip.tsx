'use client';

import { Database } from 'lucide-react';
import { sessionDbScopeLabel, shortenSessionDbPath } from '@/lib/sessionDbPath';

type SessionDatabaseChipProps = {
  path: string;
  scope?: string;
  onConfigure?: () => void;
};

export function SessionDatabaseChip({ path, scope, onConfigure }: SessionDatabaseChipProps) {
  const hasPath = Boolean((path || '').trim());
  const short = shortenSessionDbPath(path);

  return (
    <div className="shrink-0 border-b border-gov-blue-50 bg-gov-blue-50/60 px-3 py-2 max-lg:pt-12 dark:border-dark-border dark:bg-dark-bg/80 min-w-0">
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-gov-blue-200 bg-white px-2 py-1 text-[10px] font-black uppercase tracking-wide text-gov-blue-800 dark:border-dark-border dark:bg-dark-surface dark:text-dark-cyan shrink-0">
          <Database size={12} aria-hidden />
          <span className="max-sm:hidden">Base de datos de esta sesión</span>
          <span className="sm:hidden">BD sesión</span>
        </span>
        {hasPath ? (
          <button
            type="button"
            onClick={onConfigure}
            title={path}
            className="min-w-0 max-w-full rounded-lg border border-gov-blue-100 bg-white px-2.5 py-1 font-mono text-[11px] font-semibold text-gov-gray-800 hover:bg-gov-blue-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text dark:hover:bg-dark-bg break-all text-left"
          >
            {short}
          </button>
        ) : (
          <span className="text-[11px] font-semibold text-amber-800 dark:text-amber-200">
            No resuelta — abre configuración → Bóveda
          </span>
        )}
        {hasPath && (
          <span className="text-[10px] text-gov-gray-500 dark:text-dark-muted shrink-0">
            {sessionDbScopeLabel(scope)}
          </span>
        )}
      </div>
      <p className="mt-1 text-[10px] text-gov-gray-500 dark:text-dark-muted max-sm:hidden">
        RAG, reglas del agente y consultas SQL usan este mismo archivo en esta conversación.
      </p>
    </div>
  );
}
