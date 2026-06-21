'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

const DISMISS_KEY = 'duckclaw:rag-no-project-warn-dismissed';

type PlaygroundRagProjectWarningProps = {
  projectId: string;
  indexedSourceCount: number;
  onOpenRouting: () => void;
};

/** Pill compacto en la barra de composición (sin banner encima del chat). */
export function PlaygroundRagProjectWarning({
  projectId,
  indexedSourceCount,
  onOpenRouting,
}: PlaygroundRagProjectWarningProps) {
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setDismissed(sessionStorage.getItem(DISMISS_KEY) === '1');
  }, []);

  if (projectId || indexedSourceCount <= 0 || dismissed) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={onOpenRouting}
        className="inline-flex max-w-full items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-bold text-amber-950 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        title="El agente no usará RAG sin proyecto activo"
      >
        Sin proyecto RAG ({indexedSourceCount}) — elegir
      </button>
      <Link
        href="/knowledge"
        className="inline-flex rounded-full border border-amber-300 px-2 py-1 text-[10px] font-bold text-amber-950 underline dark:border-amber-800 dark:text-amber-100"
      >
        RAG
      </Link>
      <button
        type="button"
        onClick={() => {
          sessionStorage.setItem(DISMISS_KEY, '1');
          setDismissed(true);
        }}
        className="rounded-full px-1.5 py-1 text-[10px] font-bold text-amber-800 dark:text-amber-200"
        aria-label="Cerrar aviso RAG"
      >
        ×
      </button>
    </>
  );
}
