import type {
  AdminHealth,
  ReleaseWorkerCacheResult,
  FlyCommandEntry,
  OverviewMetrics,
  OverviewMetricsParams,
  WriteTaskStatusResponse,
} from '@/types/admin';

import { adminFetch } from './http';

export interface AuditEntry {
  ts: string;
  actor: string;
  action: string;
  resource: string;
  detail: string;
  meta?: Record<string, unknown>;
}

export const platformApi = {
  health: () => adminFetch<AdminHealth>('/health'),
  releaseWorkerGraphCache: () =>
    adminFetch<ReleaseWorkerCacheResult>('/gateway/release-worker-cache', { method: 'POST' }),
  getWriteTaskStatus: (taskId: string) =>
    adminFetch<WriteTaskStatusResponse>(`/write-tasks/${encodeURIComponent(taskId)}`),
  getOverviewMetrics: (params?: OverviewMetricsParams) => {
    const qs = new URLSearchParams();
    if (params?.usage_days != null) qs.set('usage_days', String(params.usage_days));
    if (params?.usage_group_by) qs.set('usage_group_by', params.usage_group_by);
    if (params?.worker_id) qs.set('worker_id', params.worker_id);
    if (params?.session_id) qs.set('session_id', params.session_id);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return adminFetch<OverviewMetrics>(`/overview/metrics${suffix}`);
  },
  getAuditLog: (limit = 100) => adminFetch<{ entries: AuditEntry[] }>(`/audit?limit=${limit}`),
  listFlyCommands: () =>
    adminFetch<{ header: string; commands: FlyCommandEntry[] }>(
      '/fly-commands'
    ),
};
