'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ExternalLink, Loader2, Wrench } from 'lucide-react';
import { adminService, type WorkerCapabilities } from '@/services/adminService';
import { TOOL_PROFILE_LABELS } from '@/lib/workerCompositionPresets';
import { DEFAULT_TOOL_PROFILE } from '@/lib/workerRoleTemplates';
import { integrationSettingsHref } from '@/lib/integrationApiKeys';

type PlaygroundWorkerCapabilitiesPanelProps = {
  workerId: string;
  refreshKey?: number;
};

export function PlaygroundWorkerCapabilitiesPanel({
  workerId,
  refreshKey,
}: PlaygroundWorkerCapabilitiesPanelProps) {
  const [payload, setPayload] = useState<WorkerCapabilities | null>(null);
  const [mcpGranted, setMcpGranted] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const id = workerId.trim();
    if (!id) {
      setPayload(null);
      setMcpGranted(0);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [capabilities, mcp] = await Promise.all([
        adminService.getWorkerCapabilities(id),
        adminService.getWorkerMcpGrants(id).catch(() => null),
      ]);
      setPayload(capabilities);
      setMcpGranted(mcp?.connectors.filter((row) => row.granted).length ?? 0);
    } catch (e) {
      setPayload(null);
      setMcpGranted(0);
      setError(e instanceof Error ? e.message : 'No se pudieron cargar capacidades');
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (!workerId.trim()) {
    return (
      <p className="px-2 py-2 text-[10px] text-gov-gray-500 dark:text-dark-muted">
        Elige un agente para ver herramientas disponibles.
      </p>
    );
  }

  if (loading && !payload) {
    return (
      <p className="flex items-center gap-2 px-2 py-2 text-[10px] text-gov-gray-500 dark:text-dark-muted">
        <Loader2 size={12} className="animate-spin" />
        Comprobando herramientas…
      </p>
    );
  }

  if (error && !payload) {
    return (
      <p className="mx-2 mb-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[10px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {error}
      </p>
    );
  }

  if (!payload) {
    return null;
  }

  const profileLabel = TOOL_PROFILE_LABELS[DEFAULT_TOOL_PROFILE];
  const optionalDeclared = payload.skills_declared;
  const gaps = payload.gaps ?? [];

  return (
    <div className="space-y-2 px-2 py-1">
      <div className="rounded-lg border border-gov-gray-100 px-2 py-2 dark:border-dark-border">
        <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
          <Wrench size={11} aria-hidden />
          Composición
        </p>
        <p className="mt-1 text-xs font-semibold text-gov-gray-900 dark:text-dark-text">{profileLabel}</p>
        <p className="mt-0.5 text-[10px] text-gov-gray-500 dark:text-dark-muted">
          {payload.skills_effective.length} skills efectivas · {payload.skills_declared.length} en manifest
          {mcpGranted > 0 ? ` · ${mcpGranted} MCP` : ''}
        </p>
        {payload.optional?.tavily ? (
          <p className="mt-1 text-[10px] text-emerald-700 dark:text-emerald-300">Research (Tavily) activo</p>
        ) : null}
        {payload.optional?.browser_sandbox ? (
          <p className="text-[10px] text-emerald-700 dark:text-emerald-300">Navegador sandbox activo</p>
        ) : null}
      </div>

      {optionalDeclared.length > 0 ? (
        <div className="px-0.5">
          <p className="text-[10px] font-medium text-gov-gray-600 dark:text-dark-muted">Extras en manifest</p>
          <p className="mt-0.5 font-mono text-[10px] leading-relaxed text-gov-gray-700 dark:text-dark-text">
            {optionalDeclared.slice(0, 8).join(', ')}
            {optionalDeclared.length > 8 ? '…' : ''}
          </p>
        </div>
      ) : null}

      {gaps.length > 0 ? (
        <ul className="space-y-1 rounded-lg border border-amber-200/80 bg-amber-50/70 px-2 py-1.5 dark:border-amber-900/40 dark:bg-amber-950/20">
          {gaps.slice(0, 4).map((gap) => (
            <li
              key={gap}
              className="flex flex-col gap-1 text-[10px] leading-snug text-amber-950 dark:text-amber-100"
            >
              <span className="flex items-start gap-1.5">
                <AlertTriangle size={11} className="mt-0.5 shrink-0" aria-hidden />
                {gap}
              </span>
              {gap.toLowerCase().includes('tavily') ? (
                <Link
                  href={integrationSettingsHref()}
                  className="pl-4 font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
                >
                  Configurar API key Tavily →
                </Link>
              ) : null}
            </li>
          ))}
          {gaps.length > 4 ? (
            <li className="text-[10px] text-amber-800 dark:text-amber-200">+{gaps.length - 4} más</li>
          ) : null}
        </ul>
      ) : null}

      <Link
        href={`/templates/${encodeURIComponent(workerId)}?focus=manifest.yaml`}
        className="flex items-center gap-1 px-0.5 text-[10px] font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
      >
        Editar herramientas del agente
        <ExternalLink size={10} aria-hidden />
      </Link>
    </div>
  );
}
