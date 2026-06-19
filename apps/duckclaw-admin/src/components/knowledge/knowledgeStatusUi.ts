import type { KnowledgeSource } from '@/services/adminService';

export type KnowledgeStatusTone = 'ready' | 'indexing' | 'pending' | 'empty' | 'unknown';

export function knowledgeStatusTone(source: KnowledgeSource): KnowledgeStatusTone {
  const status = (source.status || '').trim().toLowerCase();
  if (status === 'indexing') return 'indexing';
  if (status === 'pending') return 'pending';
  if (status === 'ready') {
    return source.chunk_count > 0 ? 'ready' : 'empty';
  }
  return 'unknown';
}

export function knowledgeStatusLabel(tone: KnowledgeStatusTone): string {
  switch (tone) {
    case 'ready':
      return 'Listo';
    case 'indexing':
      return 'Indexando';
    case 'pending':
      return 'Pendiente';
    case 'empty':
      return 'Sin chunks';
    default:
      return 'Desconocido';
  }
}

export function knowledgeStatusClass(tone: KnowledgeStatusTone): string {
  switch (tone) {
    case 'ready':
      return 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900';
    case 'indexing':
      return 'bg-sky-50 text-sky-800 border-sky-200 dark:bg-sky-950/40 dark:text-sky-200 dark:border-sky-900';
    case 'pending':
      return 'bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-900';
    case 'empty':
      return 'bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-900';
    default:
      return 'bg-gov-gray-100 text-gov-gray-700 border-gov-gray-200 dark:bg-dark-bg dark:text-dark-muted dark:border-dark-border';
  }
}

export function summarizeKnowledgeSources(sources: KnowledgeSource[]) {
  const totalChunks = sources.reduce((sum, s) => sum + (s.chunk_count || 0), 0);
  const totalDocs = sources.reduce((sum, s) => sum + (s.document_count || 0), 0);
  const readyWithChunks = sources.filter(
    (s) => (s.status || '').toLowerCase() === 'ready' && s.chunk_count > 0
  ).length;
  const indexing = sources.some((s) => (s.status || '').toLowerCase() === 'indexing');
  const allReady = sources.length > 0 && sources.every((s) => (s.status || '').toLowerCase() === 'ready');
  return { totalChunks, totalDocs, readyWithChunks, indexing, allReady };
}
