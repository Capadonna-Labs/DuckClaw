/** Etiquetas consistentes para métricas de salud en Overview. */

import { trimStr } from '@/lib/utils';

const GATEWAY_ONLINE = ['ok', 'healthy', 'up', 'online'] as const;
const GATEWAY_OFFLINE = ['off', 'down', 'error', 'unhealthy', 'degraded'] as const;

export function isGatewayHealthy(raw: string | undefined | null): boolean {
  const s = trimStr(raw).toLowerCase();
  if (!s) return false;
  if ((GATEWAY_ONLINE as readonly string[]).includes(s)) return true;
  if ((GATEWAY_OFFLINE as readonly string[]).includes(s)) return false;
  return false;
}

export function formatGatewayStatus(raw: string | undefined | null): string {
  if (!trimStr(raw)) return '—';
  return isGatewayHealthy(raw) ? 'On-line' : 'Off-line';
}

export function formatRedisStatus(connected: boolean | undefined): string {
  if (connected === undefined) return '—';
  return connected ? 'On-line' : 'Off-line';
}
