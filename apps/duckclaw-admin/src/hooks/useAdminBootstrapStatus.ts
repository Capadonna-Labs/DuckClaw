'use client';

import { useCallback, useEffect, useState } from 'react';
import type { AdminBootstrapStatus } from '@/lib/adminBootstrapStatus';

type BootstrapState = {
  status: AdminBootstrapStatus | null;
  loading: boolean;
};

const BOOTSTRAP_POLL_MS = 3_000;

export function useAdminBootstrapStatus(): BootstrapState {
  const [state, setState] = useState<BootstrapState>({ status: null, loading: true });

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/bootstrap/status', {
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
            checkedAt: new Date().toISOString(),
          } satisfies AdminBootstrapStatus),
        loading: false,
      }));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      void refresh();
    }, BOOTSTRAP_POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return state;
}
