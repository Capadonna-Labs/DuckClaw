import { adminApiKey, gatewayBase, gatewayConnectHint } from '@/lib/gatewayProxy';
import { isDesktopLiteMode } from '@/lib/desktopEnvFile';
import { GATEWAY_PM2_CANDIDATES } from '@/lib/pm2AppResolve';
import { gatewayHealthOk } from '@/lib/gatewayHealthCheck';
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

const GATEWAY_STATUS_TIMEOUT_MS = 4_000;
const PM2_CACHE_MS = 30_000;

let pm2Cache: {
  status: AdminBootstrapStatus['pm2Status'];
  restartCount: number | null;
  unstableRestarts: number | null;
  expiresAt: number;
} | null = null;

export function resetPm2BootstrapCache(): void {
  pm2Cache = null;
}

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
  unstableRestarts: number | null;
}> {
  const now = Date.now();
  if (pm2Cache && now < pm2Cache.expiresAt) {
    return {
      status: pm2Cache.status,
      restartCount: pm2Cache.restartCount,
      unstableRestarts: pm2Cache.unstableRestarts,
    };
  }
  try {
    const stdout = await pm2JlistStdout(5_000);
    const rows = parsePm2Jlist(stdout);
    if (!rows.length && !stdout) {
      const miss = { status: 'unknown' as const, restartCount: null, unstableRestarts: null };
      pm2Cache = { ...miss, expiresAt: Date.now() + PM2_CACHE_MS };
      return miss;
    }
    const gateway = rows.find((row) => {
      if (!row || typeof row !== 'object') return false;
      const name = (row as { name?: string }).name;
      return Boolean(name && GATEWAY_PM2_CANDIDATES.includes(name as (typeof GATEWAY_PM2_CANDIDATES)[number]));
    }) as {
      pm2_env?: { status?: string; restart_time?: number; unstable_restarts?: number };
    } | undefined;
    if (!gateway) {
      if (await gatewayHealthOk()) {
        const systemd = { status: 'online' as const, restartCount: null, unstableRestarts: null };
        pm2Cache = { ...systemd, expiresAt: Date.now() + PM2_CACHE_MS };
        return systemd;
      }
      const miss = { status: 'missing' as const, restartCount: null, unstableRestarts: null };
      pm2Cache = { ...miss, expiresAt: Date.now() + PM2_CACHE_MS };
      return miss;
    }
    const status = gateway.pm2_env?.status;
    const restartCount =
      typeof gateway.pm2_env?.restart_time === 'number' ? gateway.pm2_env.restart_time : null;
    const unstableRestarts =
      typeof gateway.pm2_env?.unstable_restarts === 'number'
        ? gateway.pm2_env.unstable_restarts
        : null;
    if (status === 'online' || status === 'stopped' || status === 'errored') {
      const resolved = { status, restartCount, unstableRestarts } as {
        status: AdminBootstrapStatus['pm2Status'];
        restartCount: number | null;
        unstableRestarts: number | null;
      };
      pm2Cache = { ...resolved, expiresAt: Date.now() + PM2_CACHE_MS };
      return resolved;
    }
    const unknown = { status: 'unknown' as const, restartCount, unstableRestarts };
    pm2Cache = { ...unknown, expiresAt: Date.now() + PM2_CACHE_MS };
    return unknown;
  } catch {
    const fail = { status: 'unknown' as const, restartCount: null, unstableRestarts: null };
    pm2Cache = { ...fail, expiresAt: Date.now() + PM2_CACHE_MS };
    return fail;
  }
}

async function fetchHealthWithRetry(base: string): Promise<Response> {
  const attempts = 2;
  const delayMs = 1_000;
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetchWithTimeout(`${base}/health`);
      if (res.ok) return res;
      lastErr = new Error(`HTTP ${res.status}`);
    } catch (err) {
      lastErr = err;
    }
    if (i < attempts - 1) {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error('fetch failed');
}

function baseStatusFields(pm2Status: AdminBootstrapStatus['pm2Status']) {
  const desktop = isDesktopLiteMode();
  return {
    pm2Status,
    recoveryCommand: desktop
      ? 'Reiniciar sistema (barra superior) o scripts/desktop_restart.ps1'
      : 'Reiniciar stack (botón abajo o barra superior tras login)',
  };
}

export async function resolveAdminBootstrapStatus(): Promise<AdminBootstrapStatus> {
  const base = gatewayBase();
  const key = adminApiKey();
  const checkedAt = new Date().toISOString();
  const gatewayHint = gatewayConnectHint();
  // `pm2 jlist` spawns a node process; only pay for it when the gateway looks down.
  let pm2: Awaited<ReturnType<typeof resolvePm2GatewayStatus>> | null = null;
  const resolvePm2 = async () => {
    pm2 = pm2 ?? (await resolvePm2GatewayStatus());
    return pm2;
  };

  if (!base) {
    const { status: pm2Status } = await resolvePm2();
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
    const health = await fetchHealthWithRetry(base);
    if (!health.ok) {
      const { status: pm2Status } = await resolvePm2();
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
    const down = await resolvePm2();
    const detail =
      down.unstableRestarts != null && down.unstableRestarts > 0
        ? `${err instanceof Error ? err.message : 'fetch failed'} (PM2 inestable: ${down.unstableRestarts} reinicios recientes)`
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
      ...baseStatusFields(down.status),
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
      ...baseStatusFields('online'),
      checkedAt,
    };
  }

  // /health OK is enough for login. admin/health opens DuckDB (~8s under lock) and
  // starved /auth/login + /auth/me. Key mismatch still surfaces on admin API calls.
  return {
    gatewayConfigured: true,
    gatewayReachable: true,
    adminKeyConfigured: true,
    adminKeyAccepted: true,
    canAttemptLogin: true,
    code: 'ready',
    message: 'Gateway listo para login.',
    gatewayHint,
    ...baseStatusFields('online'),
    checkedAt,
  };
}
