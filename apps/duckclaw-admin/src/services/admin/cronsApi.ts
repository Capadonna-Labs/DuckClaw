import { adminFetch } from './http';

export interface CronProcess {
  name: string;
  pm_id: number | null;
  cron: string;
  description: string | null;
  status: string | null;
  restarts: number | null;
  unstable_restarts: number | null;
  cwd: string | null;
  interpreter: string | null;
  script: string | null;
  created_at: number | null;
  pm_uptime: number | null;
}

/** /crons schedules saved per chat (clock or interval), fired by the heartbeat. */
export interface ChatSchedule {
  chat_id: string;
  kind: 'reloj' | 'intervalo';
  schedule: string;
  prompt: string;
  remove_hint: string;
  last_fire_epoch: number | null;
  source: string;
}

export interface CronActionResult {
  ok: boolean;
  stdout: string;
  stderr: string;
}

export interface CronLogsResult {
  ok: boolean;
  stdout: string;
  stderr: string;
}

export const cronsApi = {
  list: () => adminFetch<{ crons: CronProcess[] }>('/crons'),
  chatSchedules: () => adminFetch<{ schedules: ChatSchedule[] }>('/crons/chat-schedules'),
  runNow: (name: string) =>
    adminFetch<CronActionResult>(`/crons/${encodeURIComponent(name)}/run`, { method: 'POST' }),
  stop: (name: string) =>
    adminFetch<CronActionResult>(`/crons/${encodeURIComponent(name)}/stop`, { method: 'POST' }),
  start: (name: string) =>
    adminFetch<CronActionResult>(`/crons/${encodeURIComponent(name)}/start`, { method: 'POST' }),
  logs: (name: string, lines = 100) =>
    adminFetch<CronLogsResult>(`/crons/${encodeURIComponent(name)}/logs?lines=${lines}`),
};
