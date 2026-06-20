'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, X } from 'lucide-react';

const DISMISS_KEY = 'duckclaw:rag-no-project-warn-dismissed';

type PlaygroundRagProjectWarningProps = {
  projectId: string;
  indexedSourceCount: number;
  onOpenRouting: () => void;
};

export function PlaygroundRagProjectWarning({
  projectId,
  indexedSourceCount,
  onOpenRouting,
}: PlaygroundRagProjectWarningProps) {
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setDismissed(sessionStorage.getItem(DISMISS_KEY) === '1');
  }, []);

  if (projectId || indexedSourceCount <= 0 || dismissed) {
    return null;
  }

  const dismiss = () => {
    sessionStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  };

  return (
    <div className="relative shrink-0 border-b border-amber-200 bg-amber-50 px-3 py-2.5 pr-16 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <div className="absolute right-2 top-2 flex items-center gap-1">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="rounded-lg p-1.5 text-amber-800 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-900/50"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expandir aviso RAG' : 'Colapsar aviso RAG'}
        >
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
        <button
          type="button"
          onClick={dismiss}
          className="rounded-lg p-1.5 text-amber-800 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-900/50"
          aria-label="Cerrar aviso RAG"
        >
          <X size={16} />
        </button>
      </div>

      {collapsed ? (
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="text-left text-xs font-bold text-amber-900 dark:text-amber-100"
        >
          Sin proyecto RAG ({indexedSourceCount} fuente{indexedSourceCount === 1 ? '' : 's'}) — toca para ver opciones
        </button>
      ) : (
        <>
          <p className="font-bold pr-6">Hay documentos indexados pero no elegiste proyecto.</p>
          <p className="mt-0.5 text-xs text-amber-900/90 dark:text-amber-100/90">
            El agente no inyectará RAG ni usará{' '}
            <code className="font-mono">search_project_knowledge</code> sin proyecto. (
            {indexedSourceCount} fuente{indexedSourceCount === 1 ? '' : 's'} con contenido en el workspace.)
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onOpenRouting}
              className="rounded-lg bg-amber-800 px-2.5 py-1 text-xs font-black text-white hover:bg-amber-900"
            >
              Elegir proyecto
            </button>
            <Link
              href="/knowledge"
              className="rounded-lg border border-amber-300 px-2.5 py-1 text-xs font-bold text-amber-950 underline dark:border-amber-800 dark:text-amber-100"
            >
              Ver gestor RAG
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
