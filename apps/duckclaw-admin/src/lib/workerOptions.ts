/** Worker en config del gateway: string legacy o { id, label }. */
export type WorkerOption = string | { id: string; label: string };

export function workerOptionId(w: WorkerOption): string {
  return typeof w === 'string' ? w : w.id;
}

export function workerOptionLabel(w: WorkerOption): string {
  return typeof w === 'string' ? w : w.label || w.id;
}

export function workerOptionIds(workers: WorkerOption[] | undefined): string[] {
  return (workers ?? []).map(workerOptionId);
}

export function workersInclude(workers: WorkerOption[] | undefined, id: string): boolean {
  if (!id) return false;
  return workerOptionIds(workers).includes(id);
}

/** Clave canónica para emparejar workers (aliases legacy incluidos). */
export function normalizeWorkerKey(id: string): string {
  const slug = id.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!slug) return '';
  if (slug === 'platformorchestrator' || slug === 'platformorchestratorworker') {
    return 'platform-orchestrator';
  }
  if (slug === 'uidesigner' || slug === 'uidesignerworker') {
    return 'ui-designer';
  }
  return slug;
}

/** True si ambos ids refieren al mismo worker (aliases incluidos). */
export function workerMatches(a: string, b: string): boolean {
  const ka = normalizeWorkerKey(a);
  const kb = normalizeWorkerKey(b);
  if (!ka || !kb) return true;
  return ka === kb;
}
