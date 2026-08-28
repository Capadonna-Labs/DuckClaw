'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AdminBootstrapStatus } from '@/lib/adminBootstrapStatus';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';

type BootstrapState = {
  status: AdminBootstrapStatus | null;
  loading: boolean;
};

const POLL_UNHEALTHY_MS = 5_000;
const POLL_HEALTHY_MS = 60_000;

function pollIntervalMs(status: AdminBootstrapStatus | null): number {
  if (!status) return POLL_UNHEALTHY_MS;
  return status.canAttemptLogin && status.code === 'ready' ? POLL_HEALTHY_MS : POLL_UNHEALTHY_MS;
}

export function useAdminBootstrapStatus(): BootstrapState {
  const [state, setState] = useState<BootstrapState>({ status: null, loading: true });

  const refresh = useCallback(async (opts?: { nocache?: boolean }) => {
    try {
      const qs = opts?.nocache ? '?nocache=1' : '';
      const res = await fetch(`/api/admin/bootstrap/status${qs}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = (await res.json()) as AdminBootstrapStatus;
      setState({ status: data, loading: false });
    } catch {
      setState((current) => ({
        status:
          current.status ??
          ({
            gatewayConfigured: false,
            gatewayReachable: false,
            adminKeyConfigured: false,
            adminKeyAccepted: null,
            canAttemptLogin: false,
            code: 'gateway_unreachable',
            message: 'Gateway iniciando o sin responder.',
            detail: 'No se pudo consultar el estado local de bootstrap.',
            gatewayHint: 'BFF local',
            pm2Status: 'unknown',
            recoveryCommand: 'pnpm stack:up',
            checkedAt: new Date().toISOString(),
          } satisfies AdminBootstrapStatus),
        loading: false,
      }));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const intervalMs = useMemo(() => pollIntervalMs(state.status), [state.status]);
  useVisibilityAwareInterval(() => void refresh(), intervalMs);

  return { status: state.status, loading: state.loading, refresh };
}
