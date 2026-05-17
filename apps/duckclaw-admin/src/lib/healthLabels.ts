/** Etiquetas consistentes para métricas de salud en Overview. */

export function formatGatewayStatus(raw: string | undefined | null): string {
  if (raw == null || raw === '') return '—';
  const s = raw.trim().toLowerCase();
  if (['ok', 'healthy', 'up', 'online'].includes(s)) return 'En línea';
  if (['off', 'down', 'error', 'unhealthy', 'degraded'].includes(s)) return 'Fuera de línea';
  return raw.trim();
}

export function formatRedisStatus(connected: boolean | undefined): string {
  if (connected === undefined) return '—';
  return connected ? 'Conectado' : 'Desconectado';
}
