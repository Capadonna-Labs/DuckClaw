'use client';

import Link from 'next/link';

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
  if (projectId || indexedSourceCount <= 0) {
    return null;
  }

  return (
    <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <p className="font-bold">Hay documentos indexados pero no elegiste proyecto.</p>
      <p className="mt-0.5 text-xs text-amber-900/90 dark:text-amber-100/90">
        El agente no inyectará RAG ni usará <code className="font-mono">search_project_knowledge</code> sin proyecto.
        ({indexedSourceCount} fuente{indexedSourceCount === 1 ? '' : 's'} con contenido en el workspace.)
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
    </div>
  );
}
