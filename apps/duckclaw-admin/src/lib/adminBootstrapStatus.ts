import { adminApiKey, gatewayBase, gatewayConnectHint, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { parsePm2Jlist, pm2JlistStdout } from '@/lib/pm2Jlist';

export type AdminBootstrapStatus = {
  gatewayConfigured: boolean;
  gatewayReachable: boolean;
  adminKeyConfigured: boolean;
  adminKeyAccepted: boolean | null;
  canAttemptLogin: boolean;
  code: 'ready' | 'gateway_unconfigured' | 'gateway_unreachable' | 'admin_key_missing' | 'admin_key_invalid';
  message: string;
  detail?: string;
  gatewayHint: string;
  pm2Status: 'online' | 'missing' | 'stopped' | 'errored' | 'unknown';
  recoveryCommand: string;
  checkedAt: string;
};

const GATEWAY_STATUS_TIMEOUT_MS = 8_000;
const PM2_CACHE_MS = 30_000;

let pm2Cache: {
  status: AdminBootstrapStatus['pm2Status'];
  restartCount: number | null;
  expiresAt: number;
} | null = null;

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, {
    ...init,
    cache: 'no-store',
    signal: AbortSignal.timeout(GATEWAY_STATUS_TIMEOUT_MS),
  });
}

async function resolvePm2GatewayStatus(): Promise<{
  status: AdminBootstrapStatus['pm2Status'];
  restartCount: number | null;
}> {
  const now = Date.now();
  if (pm2Cache && now < pm2Cache.expiresAt) {
    return { status: pm2Cache.status, restartCount: pm2Cache.restartCount };
  }
  try {
    const stdout = await pm2JlistStdout(5_000);
    const rows = parsePm2Jlist(stdout);
    if (!rows.length && !stdout) {
      const miss = { status: 'unknown' as const, restartCount: null };
      pm2Cache = { ...miss, expiresAt: Date.now() + PM2_CACHE_MS };
      return miss;
    }
    const gateway = rows.find((row) => {
      if (!row || typeof row !== 'object') return false;
      return (row as { name?: string }).name === 'DuckClaw-Gateway';
    }) as { pm2_env?: { status?: string; restart_time?: number } } | undefined;
    if (!gateway) {
      const miss = { status: 'missing' as const, restartCount: null };
      pm2Cache = { ...miss, expiresAt: Date.now() + PM2_CACHE_MS };
      return miss;
    }
    const status = gateway.pm2_env?.status;
    const restartCount =
      typeof gateway.pm2_env?.restart_time === 'number' ? gateway.pm2_env.restart_time : null;
    if (status === 'online' || status === 'stopped' || status === 'errored') {
      const resolved = { status, restartCount } as {
        status: AdminBootstrapStatus['pm2Status'];
        restartCount: number | null;
      };
      pm2Cache = { ...resolved, expiresAt: Date.now() + PM2_CACHE_MS };
      return resolved;
    }
    const unknown = { status: 'unknown' as const, restartCount };
    pm2Cache = { ...unknown, expiresAt: Date.now() + PM2_CACHE_MS };
    return unknown;
  } catch {
    const fail = { status: 'unknown' as const, restartCount: null };
    pm2Cache = { ...fail, expiresAt: Date.now() + PM2_CACHE_MS };
    return fail;
  }
}

function baseStatusFields(pm2Status: AdminBootstrapStatus['pm2Status']) {
  return {
    pm2Status,
    recoveryCommand: 'Reiniciar stack (barra superior: migrate + PM2)',
  };
}

export async function resolveAdminBootstrapStatus(): Promise<AdminBootstrapStatus> {
  const base = gatewayBase();
  const key = adminApiKey();
  const checkedAt = new Date().toISOString();
  const gatewayHint = gatewayConnectHint();
  const pm2 = await resolvePm2GatewayStatus();
  const pm2Status = pm2.status;

  if (!base) {
    return {
      gatewayConfigured: false,
      gatewayReachable: false,
      adminKeyConfigured: Boolean(key),
      adminKeyAccepted: null,
      canAttemptLogin: false,
      code: 'gateway_unconfigured',
      message: 'Gateway no configurado para la consola admin.',
      gatewayHint,
      ...baseStatusFields(pm2Status),
      checkedAt,
    };
  }

  try {
    const health = await fetchWithTimeout(`${base}/health`);
    if (!health.ok) {
      return {
        gatewayConfigured: true,
        gatewayReachable: false,
        adminKeyConfigured: Boolean(key),
        adminKeyAccepted: null,
        canAttemptLogin: false,
        code: 'gateway_unreachable',
        message: 'Gateway iniciando o sin responder.',
        detail: `Health respondió HTTP ${health.status}`,
        gatewayHint,
        ...baseStatusFields(pm2Status),
        checkedAt,
      };
    }
  } catch (err) {
    const detail =
      pm2.restartCount != null && pm2.restartCount >= 20
        ? `${err instanceof Error ? err.message : 'fetch failed'} (PM2 reinicios: ${pm2.restartCount}; probable crash loop — usa Reiniciar stack)`
        : err instanceof Error
          ? err.message
          : 'fetch failed';
    return {
      gatewayConfigured: true,
      gatewayReachable: false,
      adminKeyConfigured: Boolean(key),
      adminKeyAccepted: null,
      canAttemptLogin: false,
      code: 'gateway_unreachable',
      message: 'Gateway iniciando o sin responder.',
      detail,
      gatewayHint,
      ...baseStatusFields(pm2Status),
      checkedAt,
    };
  }

  if (!key) {
    return {
      gatewayConfigured: true,
      gatewayReachable: true,
      adminKeyConfigured: false,
      adminKeyAccepted: false,
      canAttemptLogin: false,
      code: 'admin_key_missing',
      message: 'DUCKCLAW_ADMIN_API_KEY no está configurada en el BFF.',
      gatewayHint,
      ...baseStatusFields(pm2Status),
      checkedAt,
    };
  }

  const adminHealth = await fetchWithTimeout(`${base}/api/v1/admin/health`, {
    headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
  });
  if (adminHealth.status === 401 || adminHealth.status === 403) {
    return {
      gatewayConfigured: true,
      gatewayReachable: true,
      adminKeyConfigured: true,
      adminKeyAccepted: false,
      canAttemptLogin: false,
      code: 'admin_key_invalid',
      message: 'La clave admin del BFF no coincide con la del Gateway.',
      gatewayHint,
      ...baseStatusFields(pm2Status),
      checkedAt,
    };
  }

  return {
    gatewayConfigured: true,
    gatewayReachable: true,
    adminKeyConfigured: true,
    adminKeyAccepted: adminHealth.ok,
    canAttemptLogin: adminHealth.ok,
    code: adminHealth.ok ? 'ready' : 'gateway_unreachable',
    message: adminHealth.ok ? 'Gateway listo para login.' : `Gateway respondió HTTP ${adminHealth.status}.`,
    gatewayHint,
    ...baseStatusFields(pm2Status),
    checkedAt,
  };
}
