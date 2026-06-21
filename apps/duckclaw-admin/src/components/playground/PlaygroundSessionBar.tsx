'use client';

import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

type PlaygroundSessionBarProps = {
  summary: string;
  children: ReactNode;
};

export function PlaygroundSessionBar({ summary, children }: PlaygroundSessionBarProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="shrink-0 border-b border-gov-blue-50 bg-gov-blue-50/40 dark:border-dark-border dark:bg-dark-bg/60 max-lg:pt-11">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="lg:hidden flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span className="min-w-0 truncate text-[11px] font-black uppercase tracking-wide text-gov-blue-800 dark:text-dark-cyan">
          Sesión
        </span>
        <span className="min-w-0 flex-1 truncate text-[11px] font-semibold text-gov-gray-600 dark:text-dark-muted">
          {summary}
        </span>
        {open ? (
          <ChevronUp size={16} className="shrink-0 text-gov-gray-500" aria-hidden />
        ) : (
          <ChevronDown size={16} className="shrink-0 text-gov-gray-500" aria-hidden />
        )}
      </button>
      <div className={`${open ? 'block' : 'hidden'} lg:block min-w-0`}>{children}</div>
    </div>
  );

}
