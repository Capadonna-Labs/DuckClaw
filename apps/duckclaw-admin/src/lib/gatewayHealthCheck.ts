import { gatewayBase } from '@/lib/gatewayProxy';

const GATEWAY_HEALTH_TIMEOUT_MS = 3_000;

/** True when the API gateway responds on /health (systemd or PM2). */
export async function gatewayHealthOk(): Promise<boolean> {
  const base = gatewayBase();
  if (!base) return false;
  try {
    const res = await fetch(`${base}/health`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(GATEWAY_HEALTH_TIMEOUT_MS),
    });
    return res.ok;
  } catch {
    return false;
  }
}
