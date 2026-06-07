import { adminApiKey, gatewayBase, gatewayConnectHint, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

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

const GATEWAY_STATUS_TIMEOUT_MS = 2_500;
const PM2_JLIST_COMMAND = 'pm2 jlist';
const execFileAsync = promisify(execFile);

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, {
    ...init,
    cache: 'no-store',
    signal: AbortSignal.timeout(GATEWAY_STATUS_TIMEOUT_MS),
  });
}

async function resolvePm2GatewayStatus(): Promise<AdminBootstrapStatus['pm2Status']> {
  try {
    const [bin, arg] = PM2_JLIST_COMMAND.split(' ');
    const { stdout } = await execFileAsync(bin, [arg], { timeout: 2_000 });
    const rows = JSON.parse(stdout || '[]') as unknown;
    if (!Array.isArray(rows)) return 'unknown';
    const gateway = rows.find((row) => {
      if (!row || typeof row !== 'object') return false;
      return (row as { name?: string }).name === 'DuckClaw-Gateway';
    }) as { pm2_env?: { status?: string } } | undefined;
    if (!gateway) return 'missing';
    const status = gateway.pm2_env?.status;
    if (status === 'online' || status === 'stopped' || status === 'errored') return status;
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

function baseStatusFields(pm2Status: AdminBootstrapStatus['pm2Status']) {
  return {
    pm2Status,
    recoveryCommand: 'pnpm stack:up',
  };
}

export async function resolveAdminBootstrapStatus(): Promise<AdminBootstrapStatus> {
  const base = gatewayBase();
  const key = adminApiKey();
  const checkedAt = new Date().toISOString();
  const gatewayHint = gatewayConnectHint();
  const pm2Status = await resolvePm2GatewayStatus();

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
    return {
      gatewayConfigured: true,
      gatewayReachable: false,
      adminKeyConfigured: Boolean(key),
      adminKeyAccepted: null,
      canAttemptLogin: false,
      code: 'gateway_unreachable',
      message: 'Gateway iniciando o sin responder.',
      detail: err instanceof Error ? err.message : 'fetch failed',
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
