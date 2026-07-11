'use client';

import Link from 'next/link';
import type { KnowledgeSource } from '@/services/adminService';
import { summarizeKnowledgeSources } from '@/components/knowledge/knowledgeStatusUi';

type KnowledgeScopeStatusProps = {
  projectId: string;
  projectName?: string;
  workerId?: string;
  sources: KnowledgeSource[];
  loading: boolean;
};

export function knowledgeScopeStatusVisible(sources: KnowledgeSource[], loading: boolean): boolean {
  if (loading) return false;
  if (sources.length === 0) return true;
  const { allReady, readyWithChunks } = summarizeKnowledgeSources(sources);
  return !(allReady && readyWithChunks > 0);
}

function playgroundHref(projectId: string, workerId?: string): string {
  if (!projectId) return '/playground';
  const params = new URLSearchParams({ project: projectId });
  if (workerId) params.set('worker', workerId);
  return `/playground?${params.toString()}`;
}

export function KnowledgeScopeStatus({
  projectId,
  projectName,
  workerId,
  sources,
  loading,
}: KnowledgeScopeStatusProps) {
  if (loading) return null;

  const isFrameworkScope = !projectId;
  const { totalChunks, indexing, allReady, readyWithChunks } = summarizeKnowledgeSources(sources);
  const href = playgroundHref(projectId, workerId);
  const scopeLabel = isFrameworkScope ? 'plataforma' : projectName || 'proyecto';

  if (sources.length === 0) {
    return (
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
        Sin fuentes indexadas en {scopeLabel}.
      </p>
    );
  }

  if (allReady && readyWithChunks > 0) {
    return null;
  }

  if (indexing) {
    return (
      <p className="inline-flex flex-wrap items-center gap-2 text-sm text-sky-800 dark:text-sky-300">
        <span className="inline-block h-2 w-2 rounded-full bg-sky-500 animate-pulse" aria-hidden />
        <span className="font-bold">Indexando…</span>
        <Link href={href} className="font-bold text-gov-blue-800 underline dark:text-dark-cyan">
          Playground →
        </Link>
      </p>
    );
  }

  if (totalChunks === 0) {
    return (
      <p className="inline-flex flex-wrap items-center gap-2 text-sm text-amber-800 dark:text-amber-200">
        <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden />
        <span className="font-bold">Fuentes sin fragmentos para el chat.</span>
        {!isFrameworkScope && (
          <Link href={href} className="font-bold underline">
            Playground →
          </Link>
        )}
      </p>
    );
  }

  return (
    <p className="inline-flex flex-wrap items-center gap-2 text-sm text-gov-gray-600 dark:text-dark-muted">
      <span className="inline-block h-2 w-2 rounded-full bg-gov-gray-400" aria-hidden />
      <span className="font-bold">Algunas fuentes aún no están listas.</span>
      <Link href={href} className="font-bold text-gov-blue-800 underline dark:text-dark-cyan">
        Playground →
      </Link>
    </p>
  );
}

/** @deprecated Usa KnowledgeScopeStatus */
export function KnowledgePlaygroundBanner(props: KnowledgeScopeStatusProps) {
  return <KnowledgeScopeStatus {...props} />;
}
