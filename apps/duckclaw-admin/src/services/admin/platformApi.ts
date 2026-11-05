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

export interface PushLogEntry {
  id: string;
  title: string;
  body: string;
  tag: string;
  url: string;
  sent: number;
  failed: number;
  error: string;
  created_at: string;
}

export interface EvalCaseResult {
  type: string;
  passes: number;
  n: number;
  status: 'always_pass' | 'flaky' | 'always_fail';
  failures: string[];
  unverified?: boolean;
  sample?: { tools: string[]; reply: string; spans?: { name: string; input: string; output: string }[] };
}

export interface EvalSuiteSummary {
  suite: string;
  runnable: boolean;
  running: boolean;
  by_type: { type: string; passing: number; total: number; prev_passing: number | null; prev_total: number | null }[];
  latest: null | { ts: string; model: string; total: number; always_pass: number; flaky: number; always_fail: number; cases: Record<string, EvalCaseResult> };
  regressed: string[];
  history: { ts: string; model: string; total: number; always_pass: number; flaky: number; always_fail: number }[];
}

export const platformApi = {
  getEvalRuns: () => adminFetch<{ suites: EvalSuiteSummary[] }>('/evals/runs'),
  runEvalSuite: (suite: string) => adminFetch<{ accepted: boolean }>(`/evals/${encodeURIComponent(suite)}/run`, { method: 'POST' }),
  getPushLog: (limit = 100) => adminFetch<{ entries: PushLogEntry[] }>(`/notifications/push-log?limit=${limit}`),
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
  listWorkerLlm: (tenantId?: string) =>
    adminFetch<{ tenant_id: string; overrides: Record<string, string> }>(
      `/worker-llm?tenant_id=${encodeURIComponent(tenantId || 'default')}`
    ),
  setWorkerLlm: (body: { worker_id: string; model: string; tenant_id: string }) =>
    adminFetch<{ accepted: boolean; task_id: string }>('/worker-llm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
};
