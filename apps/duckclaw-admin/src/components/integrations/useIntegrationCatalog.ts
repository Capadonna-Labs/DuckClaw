'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService, type IntegrationCatalogResponse } from '@/services/adminService';

export function useIntegrationCatalog() {
  const [catalog, setCatalog] = useState<IntegrationCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await adminService.getIntegrationCatalog();
      setCatalog(payload);
    } catch (e) {
      setCatalog(null);
      setError(e instanceof Error ? e.message : 'No se pudo cargar el catálogo de integraciones');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { catalog, loading, error, reload };
}
