import { adminService } from '@/services/adminService';
import type { WriteTaskStatus } from '@/types/admin';

export type WriteTaskPollResult =
  | { state: 'success'; detail?: string | null }
  | { state: 'failed'; detail?: string | null }
  | { state: 'timeout' }
  | { state: 'not_found' };

const TERMINAL = new Set<WriteTaskStatus>(['success', 'failed']);

export async function pollWriteTask(
  taskId: string,
  options?: {
    intervalMs?: number;
    maxAttempts?: number;
    onTick?: (status: WriteTaskStatus) => void;
  }
): Promise<WriteTaskPollResult> {
  const intervalMs = options?.intervalMs ?? 2500;
  const maxAttempts = options?.maxAttempts ?? 120;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
    const row = await adminService.getWriteTaskStatus(taskId).catch(() => null);
    if (!row) {
      if (attempt >= 4) {
        return { state: 'not_found' };
      }
      continue;
    }
    const status = row.status;
    options?.onTick?.(status);
    if (status === 'success') {
      return { state: 'success', detail: row.detail };
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

export function formatWriteTaskPollNotice(
  result: WriteTaskPollResult,
  fallbackBusy: string
): string {
  if (result.state === 'success') {
    return result.detail ? `${fallbackBusy} completado: ${result.detail}` : `${fallbackBusy} completado.`;
  }
  if (result.state === 'failed') {
    return result.detail ? `${fallbackBusy} falló: ${result.detail}` : `${fallbackBusy} falló.`;
  }
  if (result.state === 'not_found') {
    return `${fallbackBusy} (estado de la tarea no disponible; refresca la vista).`;
  }
  return `${fallbackBusy} (tiempo de espera agotado; db-writer puede seguir procesando).`;
}
