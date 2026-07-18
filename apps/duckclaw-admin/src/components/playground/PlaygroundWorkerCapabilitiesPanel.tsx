'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import { adminService, type WorkerCapabilities } from '@/services/adminService';

type PlaygroundWorkerCapabilitiesPanelProps = {
  workerId: string;
  refreshKey?: number;
};

/** Solo avisos de runtime rotos + atajo al editor de herramientas. Sin ruido de skills/MCP opcionales. */
export function PlaygroundWorkerCapabilitiesPanel({
  workerId,
  refreshKey,
}: PlaygroundWorkerCapabilitiesPanelProps) {
  const [payload, setPayload] = useState<WorkerCapabilities | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const id = workerId.trim();
    if (!id) {
      setPayload(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const capabilities = await adminService.getWorkerCapabilities(id);
      setPayload(capabilities);
    } catch (e) {
      setPayload(null);
      setError(e instanceof Error ? e.message : 'No se pudieron cargar capacidades');
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (!workerId.trim()) {
    return null;
  }

  if (loading && !payload) {
    return (
      <p className="flex items-center gap-2 px-2 py-1 text-[10px] text-gov-gray-500 dark:text-dark-muted">
        <Loader2 size={12} className="animate-spin" />
        Comprobando…
      </p>
    );
  }

  if (error && !payload) {
    return (
      <p className="mx-2 mb-1 rounded-lg bg-amber-50 px-2 py-1.5 text-[10px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {error}
      </p>
    );
  }

  const textGaps = (payload?.gaps ?? []).filter(
    (gap) =>
      !gap.includes('falta API key') &&
      !gap.includes('sin tools MCP') &&
      !gap.includes('declarada pero sin tools') &&
      !gap.includes('catálogo UI') &&
      !gap.includes('opcional')
  );

  return (
    <div className="space-y-2 px-0.5 py-0.5">
      {textGaps.length > 0 ? (
        <ul className="space-y-1 rounded-lg border border-amber-200/80 bg-amber-50/70 px-2 py-1.5 dark:border-amber-900/40 dark:bg-amber-950/20">
          {textGaps.slice(0, 3).map((gap) => (
            <li
              key={gap}
              className="flex items-start gap-1.5 text-[10px] leading-snug text-amber-950 dark:text-amber-100"
            >
              <AlertTriangle size={11} className="mt-0.5 shrink-0" aria-hidden />
              {gap}
            </li>
          ))}
        </ul>
      ) : null}

      <Link
        href={`/templates/${encodeURIComponent(workerId)}?focus=manifest.yaml`}
        className="flex items-center gap-1 text-[10px] font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
      >
        Editar herramientas del agente
        <ExternalLink size={10} aria-hidden />
      </Link>
    </div>
  );
}
