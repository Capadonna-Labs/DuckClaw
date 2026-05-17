/** Etiquetas consistentes para métricas de salud en Overview. */

const GATEWAY_ONLINE = ['ok', 'healthy', 'up', 'online'] as const;
const GATEWAY_OFFLINE = ['off', 'down', 'error', 'unhealthy', 'degraded'] as const;

export function isGatewayHealthy(raw: string | undefined | null): boolean {
  if (raw == null || raw === '') return false;
  const s = raw.trim().toLowerCase();
  if ((GATEWAY_ONLINE as readonly string[]).includes(s)) return true;
  if ((GATEWAY_OFFLINE as readonly string[]).includes(s)) return false;
  return false;
}

export function formatGatewayStatus(raw: string | undefined | null): string {
  if (raw == null || raw === '') return '—';
  return isGatewayHealthy(raw) ? 'On-line' : 'Off-line';
}

export function formatRedisStatus(connected: boolean | undefined): string {
  if (connected === undefined) return '—';
  return connected ? 'On-line' : 'Off-line';
}
