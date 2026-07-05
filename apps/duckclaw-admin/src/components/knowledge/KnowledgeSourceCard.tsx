'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, FolderSync, Trash2 } from 'lucide-react';
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
  knowledgeSourceSecondaryLine,
} from '@/components/knowledge/knowledgeSourceLabel';
import { knowledgeStatusTone } from '@/components/knowledge/knowledgeStatusUi';

type KnowledgeSourceCardProps = {
  source: KnowledgeSource;
  projectId: string;
  busy: boolean;
  jobProgress?: KnowledgeJobProgress | null;
  expectedFileTotal?: number;
  onSync: (source: KnowledgeSource) => void;
  onDelete: (source: KnowledgeSource) => void;
};

export function KnowledgeSourceCard({
  source,
  projectId,
  busy,
  jobProgress,
  expectedFileTotal,
  onSync,
  onDelete,
}: KnowledgeSourceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const secondary = knowledgeSourceSecondaryLine(source);
  const hasLongDetail = Boolean(secondary && secondary.length > 72);
  const tone = knowledgeStatusTone(source);
  const metadataFileCount =
    typeof source.metadata?.file_count === 'number' ? source.metadata.file_count : undefined;

  return (
    <div className="rounded-2xl border border-gov-blue-50 dark:border-dark-border overflow-hidden">
      <div className="flex flex-col gap-3 p-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-black text-gov-gray-900 dark:text-dark-text break-words">
              {knowledgeSourcePrimaryLabel(source)}
            </p>
            <KnowledgeStatusBadge source={source} />
          </div>
          <p className="mt-2 text-xs text-gov-gray-500 dark:text-dark-muted">
            {source.document_count} documento{source.document_count === 1 ? '' : 's'} ·{' '}
            {source.chunk_count} fragmento{source.chunk_count === 1 ? '' : 's'} para el chat
            {knowledgeSourceLastSyncLabel(source) && (
              <> · última sync {knowledgeSourceLastSyncLabel(source)}</>
            )}
          </p>
          {tone === 'indexing' && (
            <KnowledgeIndexingProgress
              progress={jobProgress}
              documentCount={source.document_count}
              chunkCount={source.chunk_count}
              expectedTotal={expectedFileTotal ?? metadataFileCount}
            />
          )}
          {hasLongDetail && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-gov-blue-800 dark:text-dark-cyan"
            >
              {expanded ? (
                <>
                  Ocultar archivos <ChevronUp size={14} />
                </>
              ) : (
                <>
                  Ver archivos <ChevronDown size={14} />
                </>
              )}
            </button>
          )}
          {(expanded || !hasLongDetail) && secondary && (
            <p className="mt-1 break-all font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
              {secondary}
            </p>
          )}
          {(expanded || !hasLongDetail) && (
            <p className="mt-1 break-all font-mono text-[10px] text-gov-gray-400 dark:text-dark-muted/80">
              {source.source_id}
            </p>
          )}
          {source.chunk_count === 0 && (
            <Link
              href={`/playground?project=${encodeURIComponent(projectId)}`}
              className="mt-2 inline-block text-xs font-bold text-gov-blue-800 underline dark:text-dark-cyan"
            >
              El agente no verá contenido hasta que haya fragmentos — probar en Playground →
            </Link>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {isFolderKnowledgeSource(source) && (
            <button
              type="button"
              onClick={() => onSync(source)}
              disabled={busy}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
            >
              <FolderSync size={14} />
              Sincronizar
            </button>
          )}
          <button
            type="button"
            onClick={() => onDelete(source)}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/60 dark:text-red-300"
            title="Elimina documentos y fragmentos indexados del chat"
          >
            <Trash2 size={14} />
            Eliminar del RAG
          </button>
        </div>
      </div>
    </div>
  );
}
