'use client';

import { useCallback, useEffect, useState } from 'react';
import { isTauriDesktop } from '@/lib/tauriRuntime';

type UpdateHandle = {
  version: string;
  downloadAndInstall: (
    onEvent?: (event: { event: string; data?: { percent?: number } }) => void
  ) => Promise<void>;
};

export function useAutoUpdate() {
  const [update, setUpdate] = useState<UpdateHandle | null>(null);
  const [checking, setChecking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauriDesktop()) return;
    let cancelled = false;
    setChecking(true);
    (async () => {
      try {
        const { check } = await import('@tauri-apps/plugin-updater');
        const found = await check();
        if (!cancelled && found) {
          setUpdate(found as UpdateHandle);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'No se pudo comprobar actualizaciones');
        }
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const installAndRestart = useCallback(async () => {
    if (!update || !isTauriDesktop()) return;
    setDownloading(true);
    setError(null);
    setProgress(0);
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('prepare_for_update');
      await update.downloadAndInstall((event) => {
        if (event.event === 'Progress' && typeof event.data?.percent === 'number') {
          setProgress(event.data.percent);
        }
      });
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al instalar la actualización');
      setDownloading(false);
    }
  }, [update]);

  return {
    available: Boolean(update),
    version: update?.version ?? null,
    checking,
    downloading,
    progress,
    error,
    installAndRestart,
  };
}
