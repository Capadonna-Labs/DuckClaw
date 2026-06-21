const LAST_WORKER_KEY = 'duckclaw-admin-last-created-worker';

export function readLastCreatedWorker(): string {
  if (typeof window === 'undefined') return '';
  try {
    return (localStorage.getItem(LAST_WORKER_KEY) || '').trim();
  } catch {
    return '';
  }
}

export function writeLastCreatedWorker(workerId: string): void {
  if (typeof window === 'undefined') return;
  const id = (workerId || '').trim();
  try {
    if (id) localStorage.setItem(LAST_WORKER_KEY, id);
    else localStorage.removeItem(LAST_WORKER_KEY);
  } catch {
    /* ignore */
  }
}

export { readLastProjectId, writeLastProjectId } from '@/lib/floatingChatProject';

export function playgroundHref(projectId?: string, workerId?: string): string {
  const params = new URLSearchParams();
  const project = (projectId || '').trim();
  const worker = (workerId || '').trim();
  if (project) params.set('project', project);
  if (worker) params.set('worker', worker);
  const qs = params.toString();
  return qs ? `/playground?${qs}` : '/playground';
}

export function knowledgeHref(projectId?: string, workerId?: string): string {
  const params = new URLSearchParams();
  const project = (projectId || '').trim();
  const worker = (workerId || '').trim();
  if (project) params.set('project', project);
  if (worker) params.set('worker', worker);
  const qs = params.toString();
  return qs ? `/knowledge?${qs}` : '/knowledge';
}
