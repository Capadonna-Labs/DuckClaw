import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { adminService } from '@/services/adminService';
import { formatWriteTaskPollNotice, pollWriteTask } from './pollWriteTask';

vi.mock('@/services/adminService', () => ({
  adminService: {
    getWriteTaskStatus: vi.fn(),
  },
}));

const getWriteTaskStatus = vi.mocked(adminService.getWriteTaskStatus);

describe('pollWriteTask', () => {
  beforeEach(() => {
    vi.stubGlobal('window', globalThis);
    vi.useFakeTimers();
    getWriteTaskStatus.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns success when db-writer confirms', async () => {
    getWriteTaskStatus
      .mockResolvedValueOnce({ task_id: 'task-1', status: 'pending', detail: null })
      .mockResolvedValueOnce({ task_id: 'task-1', status: 'success', detail: 'applied 3 policies' });

    const pollPromise = pollWriteTask('task-1', { intervalMs: 100, maxAttempts: 5 });
    await vi.advanceTimersByTimeAsync(200);
    await expect(pollPromise).resolves.toEqual({
      state: 'success',
      detail: 'applied 3 policies',
    });
  });

  it('returns failed when db-writer reports failure', async () => {
    getWriteTaskStatus.mockResolvedValueOnce({
      task_id: 'task-2',
      status: 'failed',
      detail: 'constraint violation',
    });

    const pollPromise = pollWriteTask('task-2', { intervalMs: 100, maxAttempts: 3 });
    await vi.advanceTimersByTimeAsync(100);
    await expect(pollPromise).resolves.toEqual({
      state: 'failed',
      detail: 'constraint violation',
    });
  });

  it('returns timeout after max attempts while pending', async () => {
    getWriteTaskStatus.mockResolvedValue({ task_id: 'task-3', status: 'pending', detail: null });

    const pollPromise = pollWriteTask('task-3', { intervalMs: 50, maxAttempts: 3 });
    await vi.advanceTimersByTimeAsync(150);
    await expect(pollPromise).resolves.toEqual({ state: 'timeout' });
    expect(getWriteTaskStatus).toHaveBeenCalledTimes(3);
  });

  it('returns not_found when status endpoint keeps failing', async () => {
    getWriteTaskStatus.mockRejectedValue(new Error('network'));

    const pollPromise = pollWriteTask('task-4', { intervalMs: 10, maxAttempts: 8 });
    await vi.advanceTimersByTimeAsync(50);
    await expect(pollPromise).resolves.toEqual({ state: 'not_found' });
    expect(getWriteTaskStatus).toHaveBeenCalledTimes(5);
  });
});

describe('formatWriteTaskPollNotice', () => {
  it('formats terminal states', () => {
    expect(formatWriteTaskPollNotice({ state: 'success', detail: 'ok' }, 'Restore')).toBe(
      'Restore completado: ok'
    );
    expect(formatWriteTaskPollNotice({ state: 'failed', detail: 'boom' }, 'Sync')).toBe(
      'Sync falló: boom'
    );
    expect(formatWriteTaskPollNotice({ state: 'timeout' }, 'Restore')).toContain('tiempo de espera agotado');
    expect(formatWriteTaskPollNotice({ state: 'not_found' }, 'Sync')).toContain('no disponible');
  });
});
