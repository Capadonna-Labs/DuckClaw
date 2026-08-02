'use client';

import { RefreshCw } from 'lucide-react';
import type { KnowledgeSource } from '@/services/adminService';
import { KnowledgeSourceCard } from '@/components/knowledge/KnowledgeSourceCard';
import { summarizeKnowledgeSources } from '@/components/knowledge/knowledgeStatusUi';
import type { KnowledgeJobProgress } from '@/lib/pollKnowledgeSyncJob';

type IndexingJobState = {
  progress?: KnowledgeJobProgress;
  expectedFiles?: number;
  jobStatus?: string | null;
  errorMessage?: string | null;
};

export type KnowledgeSourcesGridProps = {
  projectId: string;
  sources: KnowledgeSource[];
  loading: boolean;
  busy: boolean;
  indexingJobs: Record<string, IndexingJobState>;
  onRefresh: () => void;
  onSync: (source: KnowledgeSource) => void;
  onDelete: (source: KnowledgeSource) => void;
};

function sourcesSummaryLabel(sources: KnowledgeSource[]): string | null {
  if (sources.length === 0) return null;
  const { totalChunks, totalDocs } = summarizeKnowledgeSources(sources);
  const n = sources.length;
  return `${n} fuente${n === 1 ? '' : 's'} · ${totalDocs} doc${totalDocs === 1 ? '' : 's'} · ${totalChunks} frag.`;
}

export function KnowledgeSourcesGrid({
  projectId,
  sources,
  loading,
  busy,
  indexingJobs,
  onRefresh,
  onSync,
  onDelete,
}: KnowledgeSourcesGridProps) {
  const summary = sourcesSummaryLabel(sources);

  return (
    <section className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">En el chat</h2>
          {summary ? (
            <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">{summary}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-blue-800 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
        >
          <RefreshCw size={14} />
          Refrescar
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Cargando fuentes…</p>
      ) : sources.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gov-gray-200 p-8 text-center dark:border-dark-border">
          <p className="text-sm font-bold text-gov-gray-700 dark:text-dark-text">Sin fuentes registradas</p>
          <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
            {projectId
              ? 'Indexa una carpeta desde el panel izquierdo para este proyecto.'
              : 'Indexa una carpeta con alcance Plataforma desde el panel izquierdo.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,220px),1fr))] gap-3">
          {sources.map((source) => (
            <KnowledgeSourceCard
              key={source.source_id}
              source={source}
              busy={busy}
              jobProgress={indexingJobs[source.source_id]?.progress}
              expectedFileTotal={
                indexingJobs[source.source_id]?.expectedFiles ??
                (typeof source.metadata?.file_count === 'number' ? source.metadata.file_count : undefined)
              }
              jobStatus={indexingJobs[source.source_id]?.jobStatus}
              errorMessage={indexingJobs[source.source_id]?.errorMessage}
              onSync={onSync}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </section>
  );
}
