import { adminService } from '@/services/adminService';

export type KnowledgeSyncJobPollResult =
  | { state: 'completed'; detail?: string }
  | { state: 'failed'; detail?: string }
  | { state: 'timeout' }
  | { state: 'not_found' };

const TERMINAL = new Set(['completed', 'failed']);

export async function pollKnowledgeSyncJob(
  jobId: string,
  options?: {
    intervalMs?: number;
    maxAttempts?: number;
    onTick?: (status: string) => void;
  }
): Promise<KnowledgeSyncJobPollResult> {
  const intervalMs = options?.intervalMs ?? 2500;
  const maxAttempts = options?.maxAttempts ?? 120;

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
    options?.onTick?.(status);
    if (status === 'completed') {
      return { state: 'completed', detail: row.detail };
    }
    if (status === 'failed') {
      return { state: 'failed', detail: row.detail };
    }
    if (TERMINAL.has(status)) {
      return { state: 'failed', detail: row.detail };
    }
  }
  return { state: 'timeout' };
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
