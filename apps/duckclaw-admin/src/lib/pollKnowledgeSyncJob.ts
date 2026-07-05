import { adminService } from '@/services/adminService';

export type KnowledgeSyncJobPollResult =
  | { state: 'completed'; detail?: string; progress?: KnowledgeJobProgress }
  | { state: 'failed'; detail?: string; progress?: KnowledgeJobProgress }
  | { state: 'timeout'; progress?: KnowledgeJobProgress }
  | { state: 'not_found' };

export type KnowledgeJobProgress = {
  files_total?: number;
  files_done?: number;
  chunks_done?: number;
  phase?: string;
  current_file?: string;
};

const TERMINAL = new Set(['completed', 'failed']);

export async function pollKnowledgeSyncJob(
  jobId: string,
  options?: {
    intervalMs?: number;
    maxAttempts?: number;
    onTick?: (status: string, progress?: KnowledgeJobProgress) => void;
  }
): Promise<KnowledgeSyncJobPollResult> {
  const intervalMs = options?.intervalMs ?? 2500;
  const maxAttempts = options?.maxAttempts ?? 120;
  let lastProgress: KnowledgeJobProgress | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
    const row = await adminService.getKnowledgeSyncJobStatus(jobId).catch(() => null);
    if (!row) {
      if (attempt >= 4) {
        return { state: 'not_found' };
      }
      continue;
    }
    const status = row.status;
    const progress = row.progress;
    if (progress) {
      lastProgress = progress;
    }
    options?.onTick?.(status, progress);
    if (status === 'completed') {
      return { state: 'completed', detail: row.detail, progress: lastProgress };
    }
    if (status === 'failed') {
      return { state: 'failed', detail: row.detail, progress: lastProgress };
    }
    if (TERMINAL.has(status)) {
      return { state: 'failed', detail: row.detail, progress: lastProgress };
    }
  }
  return { state: 'timeout', progress: lastProgress };
}

export function formatKnowledgeJobPollNotice(
  result: KnowledgeSyncJobPollResult,
  fallbackBusy: string
): string {
  if (result.state === 'completed') {
    return 'Indexación completada.';
  }
  if (result.state === 'failed') {
    return result.detail ? `Indexación falló: ${result.detail}` : 'Indexación falló.';
  }
  if (result.state === 'not_found') {
    return `${fallbackBusy} (estado del job no disponible; refresca la lista).`;
  }
  return `${fallbackBusy} (tiempo de espera agotado; el indexer puede seguir trabajando).`;
}
