'use client';

import { ChevronDown, ChevronUp } from 'lucide-react';

type ScrollFabPairProps = {
  showScrollTop: boolean;
  showScrollBottom: boolean;
  onScrollTop: () => void;
  onScrollBottom: () => void;
  className?: string;
};

/** FABs de scroll arriba/abajo (mismo estilo que AdminChatPanel). */
export function ScrollFabPair({
  showScrollTop,
  showScrollBottom,
  onScrollTop,
  onScrollBottom,
  className = '',
}: ScrollFabPairProps) {
  if (!showScrollTop && !showScrollBottom) return null;

  return (
    <div className={`pointer-events-none fixed bottom-24 right-6 z-20 flex flex-col gap-2 ${className}`}>
      {showScrollTop && (
        <button
          type="button"
          onClick={onScrollTop}
          className="pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full bg-gov-blue-700 text-white shadow-lg ring-2 ring-white/80 hover:bg-gov-blue-800 dark:ring-dark-surface"
          aria-label="Ir arriba"
          title="Ir arriba"
        >
          <ChevronUp size={20} aria-hidden />
        </button>
      )}
      {showScrollBottom && (
        <button
          type="button"
          onClick={onScrollBottom}
          className="pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full bg-gov-blue-700 text-white shadow-lg ring-2 ring-white/80 hover:bg-gov-blue-800 dark:ring-dark-surface"
          aria-label="Ir abajo"
          title="Ir abajo"
        >
          <ChevronDown size={20} aria-hidden />
        </button>
      )}
    </div>
  );
}
