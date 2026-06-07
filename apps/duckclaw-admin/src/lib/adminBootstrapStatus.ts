import { adminApiKey, gatewayBase, gatewayConnectHint, gatewayProxyHeaders } from '@/lib/gatewayProxy';

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
  checkedAt: string;
};

const GATEWAY_STATUS_TIMEOUT_MS = 2_500;

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, {
    ...init,
    cache: 'no-store',
    signal: AbortSignal.timeout(GATEWAY_STATUS_TIMEOUT_MS),
  });
}

export async function resolveAdminBootstrapStatus(): Promise<AdminBootstrapStatus> {
  const base = gatewayBase();
  const key = adminApiKey();
  const checkedAt = new Date().toISOString();
  const gatewayHint = gatewayConnectHint();

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
    checkedAt,
  };
}
