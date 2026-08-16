'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2, Settings2, Wrench } from 'lucide-react';
import { adminService, type WorkerCapabilities } from '@/services/adminService';
import { parseManifestQuick } from '@/lib/manifestQuickEdit';
import { parseManifestSkills } from '@/lib/manifestSkillsEdit';
import { TOOL_PROFILE_LABELS } from '@/lib/workerCompositionPresets';

type WorkerCapabilitiesCardProps = {
  workerId: string;
  manifestYaml: string;
  manifestDirty?: boolean;
  canEdit?: boolean;
  refreshKey?: string | null;
  onOpenManifest?: () => void;
};

export function WorkerCapabilitiesCard({
  workerId,
  manifestYaml,
  manifestDirty,
  canEdit,
  refreshKey,
  onOpenManifest,
}: WorkerCapabilitiesCardProps) {
  const [payload, setPayload] = useState<WorkerCapabilities | null>(null);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const manifestQuick = useMemo(() => parseManifestQuick(manifestYaml), [manifestYaml]);
  const optionalSkills = useMemo(
    () => parseManifestSkills(manifestYaml).optionalSkillNames,
    [manifestYaml]
  );
  const profileLabel = TOOL_PROFILE_LABELS[manifestQuick.toolProfile] ?? 'Asistente completo';
  const runtimeGaps = payload?.gaps ?? [];

  const load = useCallback(async () => {
    if (!workerId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.getWorkerCapabilities(workerId);
      if (data) {
        setPayload(data);
        setApiUnavailable(false);
      } else {
        setPayload(null);
        setApiUnavailable(true);
      }
    } catch (e) {
      setPayload(null);
      setApiUnavailable(true);
      setError(e instanceof Error ? e.message : 'No se pudieron cargar capabilities');
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey, optionalSkills]);

  const showRuntimeSection = loading || apiUnavailable || Boolean(error) || runtimeGaps.length > 0;

  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
            <Wrench size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
            Herramientas del worker
          </p>
          <p className="mt-1 text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Perfil: <span className="font-semibold text-gov-gray-700 dark:text-dark-text">{profileLabel}</span>
            {optionalSkills.length > 0 ? (
              <>
                {' '}
                · extras:{' '}
                <span className="font-mono text-[10px]">{optionalSkills.join(', ')}</span>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {manifestDirty ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              sin guardar
            </span>
          ) : null}
          {canEdit && onOpenManifest ? (
            <button
              type="button"
              onClick={onOpenManifest}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gov-blue-800"
            >
              <Settings2 size={14} />
              Configurar herramientas
            </button>
          ) : null}
        </div>
      </div>

      {showRuntimeSection ? (
        <div className="space-y-3 px-4 py-3">
          {loading ? (
            <p className="flex items-center gap-2 text-xs text-gov-gray-500 dark:text-dark-muted">
              <Loader2 size={14} className="animate-spin" />
              Comprobando runtime…
            </p>
          ) : null}
          {apiUnavailable && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-[11px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              No se pudo comprobar el runtime del worker.
            </p>
          )}
          {error && !apiUnavailable && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </p>
          )}
          {runtimeGaps.length > 0 ? (
            <ul className="space-y-1.5 rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/20">
              {runtimeGaps.map((gap) => (
                <li
                  key={gap}
                  className="flex items-start gap-2 text-[11px] text-amber-950 dark:text-amber-100"
                >
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  {gap}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
