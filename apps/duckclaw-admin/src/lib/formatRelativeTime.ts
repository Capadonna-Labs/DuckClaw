/** Etiqueta relativa en español para timestamps del cliente (ms epoch). */
export function formatRelativeTimeMs(timestampMs: number | null | undefined): string {
  if (timestampMs == null || timestampMs <= 0) {
    return 'sin datos';
  }
  const diffMs = Date.now() - timestampMs;
  if (diffMs < 0) {
    return 'ahora';
  }
  const secs = Math.floor(diffMs / 1000);
  if (secs < 10) {
    return 'ahora';
  }
  if (secs < 60) {
    return `hace ${secs}s`;
  }
  const mins = Math.floor(secs / 60);
  if (mins < 60) {
    return `hace ${mins}m`;
  }
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) {
    return `hace ${hrs}h`;
  }
  const days = Math.floor(hrs / 24);
  if (days < 7) {
    return `hace ${days}d`;
  }
  return new Date(timestampMs).toLocaleDateString();
}
