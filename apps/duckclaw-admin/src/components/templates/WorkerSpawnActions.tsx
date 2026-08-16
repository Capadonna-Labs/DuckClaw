'use client';

import { useCallback, useState } from 'react';
import { Download, Globe, Package } from 'lucide-react';
import { adminService } from '@/services/adminService';

function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof Error && e.message.trim()) return e.message;
  if (typeof e === 'string' && e.trim()) return e;
  if (e && typeof e === 'object') {
    const detail = (e as { detail?: unknown; message?: unknown }).detail
      ?? (e as { message?: unknown }).message;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail && typeof detail === 'object') {
      const inner = detail as { detail?: unknown; title?: unknown };
      if (typeof inner.detail === 'string' && inner.detail.trim()) return inner.detail;
      if (typeof inner.title === 'string' && inner.title.trim()) return inner.title;
    }
  }
  return fallback;
}

type Props = {
  workerId: string;
  a2aDiscoverable?: boolean;
  canWrite?: boolean;
  onDiscoverableChange?: (value: boolean) => void;
};

export function WorkerSpawnActions({
  workerId,
  a2aDiscoverable = false,
  canWrite = false,
  onDiscoverableChange,
}: Props) {
  const [busy, setBusy] = useState<'card' | 'spawn' | 'discover' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const downloadAgentCard = useCallback(async () => {
    setBusy('card');
    setError(null);
    try {
      const card = await adminService.fetchAgentCard(workerId);
      const blob = new Blob([JSON.stringify(card, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${workerId}-agent-card.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errorMessage(e, 'Error al descargar Agent Card'));
    } finally {
      setBusy(null);
    }
  }, [workerId]);

  const downloadSpawnPackage = useCallback(async () => {
    setBusy('spawn');
    setError(null);
    try {
      await adminService.downloadSpawnPackage(workerId);
    } catch (e) {
      setError(errorMessage(e, 'Error al descargar paquete'));
    } finally {
      setBusy(null);
    }
  }, [workerId]);

  const toggleDiscoverable = useCallback(async () => {
    if (!canWrite) return;
    setBusy('discover');
    setError(null);
    try {
      const next = !a2aDiscoverable;
      await adminService.setA2aDiscoverable(workerId, next);
      onDiscoverableChange?.(next);
    } catch (e) {
      setError(errorMessage(e, 'Error al actualizar discovery'));
    } finally {
      setBusy(null);
    }
  }, [a2aDiscoverable, canWrite, onDiscoverableChange, workerId]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={downloadAgentCard}
          disabled={busy !== null}
          className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm dark:border-dark-border"
        >
          <Download size={16} />
          {busy === 'card' ? 'Descargando…' : 'Agent Card (A2A)'}
        </button>
        <button
          type="button"
          onClick={downloadSpawnPackage}
          disabled={busy !== null}
          className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm dark:border-dark-border"
        >
          <Package size={16} />
          {busy === 'spawn' ? 'Empaquetando…' : 'Paquete spawn'}
        </button>
        {canWrite ? (
          <button
            type="button"
            onClick={toggleDiscoverable}
            disabled={busy !== null}
            className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
              a2aDiscoverable
                ? 'border-emerald-400 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
                : 'dark:border-dark-border'
            }`}
          >
            <Globe size={16} />
            {busy === 'discover'
              ? '…'
              : a2aDiscoverable
                ? 'Discovery público ON'
                : 'Discovery público OFF'}
          </button>
        ) : null}
      </div>
      {error ? (
        <p className="text-xs text-red-600 dark:text-red-300">{error}</p>
      ) : null}
    </div>
  );
}
