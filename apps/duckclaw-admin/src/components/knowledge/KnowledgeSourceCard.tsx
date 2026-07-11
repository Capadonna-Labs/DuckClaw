'use client';

import type { KnowledgeSource } from '@/services/adminService';
import { KnowledgeStatusBadge } from '@/components/knowledge/KnowledgeStatusBadge';
import {
  KnowledgeIndexingProgress,
  type KnowledgeJobProgress,
} from '@/components/knowledge/KnowledgeIndexingProgress';
import {
  isFolderKnowledgeSource,
  knowledgeSourceLastSyncLabel,
  knowledgeSourcePrimaryLabel,
} from '@/components/knowledge/knowledgeSourceLabel';
import { knowledgeStatusTone } from '@/components/knowledge/knowledgeStatusUi';
import { FolderSync, Trash2 } from 'lucide-react';

type KnowledgeSourceCardProps = {
  source: KnowledgeSource;
  busy: boolean;
  jobProgress?: KnowledgeJobProgress | null;
  expectedFileTotal?: number;
  jobStatus?: string | null;
  errorMessage?: string | null;
  onSync: (source: KnowledgeSource) => void;
  onDelete: (source: KnowledgeSource) => void;
};

export function KnowledgeSourceCard({
  source,
  busy,
  jobProgress,
  expectedFileTotal,
  jobStatus,
  errorMessage,
  onSync,
  onDelete,
}: KnowledgeSourceCardProps) {
  const label = knowledgeSourcePrimaryLabel(source);
  const tone = knowledgeStatusTone(source);
  const syncLabel = knowledgeSourceLastSyncLabel(source);
  const metadataFileCount =
    typeof source.metadata?.file_count === 'number' ? source.metadata.file_count : undefined;

  return (
    <article className="flex min-h-[140px] flex-col rounded-2xl border border-gov-gray-100 bg-white p-3.5 shadow-sm transition-all hover:border-gov-blue-200 dark:border-dark-border dark:bg-dark-surface">
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p
            className="min-w-0 flex-1 truncate text-sm font-black text-gov-gray-900 dark:text-dark-text"
            title={label}
          >
            {label}
          </p>
          <KnowledgeStatusBadge source={source} />
        </div>
        {syncLabel ? (
          <p className="mt-1.5 truncate text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Sync {syncLabel}
          </p>
        ) : null}
        {tone === 'indexing' && (
          <KnowledgeIndexingProgress
            progress={jobProgress}
            documentCount={source.document_count}
            chunkCount={source.chunk_count}
            expectedTotal={expectedFileTotal ?? metadataFileCount}
            jobStatus={jobStatus}
            errorMessage={errorMessage}
          />
        )}
        {source.chunk_count === 0 && source.status !== 'ready' && (
          <p className="mt-2 text-xs text-amber-800 dark:text-amber-200">
            Sin fragmentos indexados. Sincroniza o reimporta.
          </p>
        )}
      </div>

      <div className="mt-auto flex flex-wrap items-center justify-end gap-1.5 border-t border-gov-gray-100 pt-2.5 dark:border-dark-border">
        {isFolderKnowledgeSource(source) && (
          <button
            type="button"
            onClick={() => onSync(source)}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
            title="Sincronizar carpeta"
          >
            <FolderSync size={14} />
            Sync
          </button>
        )}
        <button
          type="button"
          onClick={() => onDelete(source)}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-bold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/60 dark:text-red-300"
          title="Eliminar del RAG"
          aria-label="Eliminar del RAG"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </article>
  );
}
