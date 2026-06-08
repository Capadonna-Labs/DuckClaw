'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';

export type McpCatalog = Awaited<ReturnType<typeof adminService.getMcpCatalog>>;
export type McpLive = Awaited<ReturnType<typeof adminService.getMcpLiveStatus>>;

export function useMcpCatalog() {
  const [data, setData] = useState<McpCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshCatalog = useCallback(() => {
    setError(null);
    return adminService
      .getMcpCatalog()
      .then((catalog) => {
        setData(catalog);
        return catalog;
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Error');
        throw e;
      });
  }, []);

  useEffect(() => {
    refreshCatalog().catch(() => undefined);
  }, [refreshCatalog]);

  return { data, error, refreshCatalog };
}

export function useMcpLiveStatus() {
  const [live, setLive] = useState<McpLive | null>(null);

  const refreshLive = useCallback(() => {
    return adminService.getMcpLiveStatus().then(setLive).catch(() => setLive(null));
  }, []);

  useEffect(() => {
    refreshLive();
  }, [refreshLive]);

  return { live, setLive, refreshLive };
}
