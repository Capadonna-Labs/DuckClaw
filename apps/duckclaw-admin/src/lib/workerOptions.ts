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
