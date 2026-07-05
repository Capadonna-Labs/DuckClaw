'use client';

export type KnowledgeJobProgress = {
  files_total?: number;
  files_done?: number;
  chunks_done?: number;
  phase?: string;
  current_file?: string;
};

type KnowledgeIndexingProgressProps = {
  progress?: KnowledgeJobProgress | null;
  documentCount?: number;
  chunkCount?: number;
  expectedTotal?: number;
};

export function KnowledgeIndexingProgress({
  progress,
  documentCount = 0,
  chunkCount = 0,
  expectedTotal,
}: KnowledgeIndexingProgressProps) {
  const total = progress?.files_total ?? expectedTotal ?? 0;
  const done = Math.max(progress?.files_done ?? 0, documentCount);
  const chunks = Math.max(progress?.chunks_done ?? 0, chunkCount);
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const indeterminate = total <= 0;

  return (
    <div className="mt-3" role="status" aria-live="polite">
      <div className="h-2 overflow-hidden rounded-full bg-gov-gray-100 dark:bg-dark-bg">
        {indeterminate ? (
          <div className="relative h-full w-full overflow-hidden">
            <div className="absolute inset-y-0 w-1/3 animate-pulse rounded-full bg-sky-500" />
          </div>
        ) : (
          <div
            className="h-full rounded-full bg-sky-500 transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      <p className="mt-1.5 text-[11px] text-gov-gray-600 dark:text-dark-muted">
        {indeterminate
          ? 'Indexando… esperando conteo de archivos'
          : `${done} / ${total} archivos (${pct}%) · ${chunks} fragmento${chunks === 1 ? '' : 's'}`}
      </p>
      {progress?.current_file && (
        <p className="mt-0.5 truncate font-mono text-[10px] text-gov-gray-400 dark:text-dark-muted/80">
          {progress.current_file}
        </p>
      )}
    </div>
  );
}
