/** Normalized key the gateway stores per worker (``normalize_runtime_setting_name``). */
export function workerLlmKey(workerId: string): string {
  return workerId.trim().toLowerCase().replace(/[^a-z0-9_.-]+/g, '_').replace(/^[_.-]+|[_.-]+$/g, '');
}
