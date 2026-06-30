'use client';

import { useCallback, useEffect, useState } from 'react';
import { Container, Loader2, Wrench } from 'lucide-react';
import { adminService, type WorkerCapabilities } from '@/services/adminService';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';
import { WorkerToolsDropdown } from '@/components/templates/WorkerToolsDropdown';

type WorkerCapabilitiesCardProps = {
  workerId: string;
  manifestYaml: string;
  onManifestChange: (nextYaml: string) => void;
  manifestDirty?: boolean;
  canEdit?: boolean;
  refreshKey?: string | null;
};

export function WorkerCapabilitiesCard({
  workerId,
  manifestYaml,
  onManifestChange,
  manifestDirty,
  canEdit,
  refreshKey,
}: WorkerCapabilitiesCardProps) {
  const [payload, setPayload] = useState<WorkerCapabilities | null>(null);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { globalSkills, localSkills } = useSkillsCatalog();

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
  }, [load, refreshKey]);

  return (
    <section className="rounded-2xl border border-gov-gray-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
            <Wrench size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
            Capabilities del worker
          </p>
          <p className="mt-1 text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Estado del sandbox y herramientas opcionales del manifest.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {manifestDirty ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-black uppercase text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              manifest sin guardar
            </span>
          ) : null}
          {payload?.framework_baseline ? (
            <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-black uppercase text-green-800 dark:bg-green-950/40 dark:text-green-300">
              baseline
            </span>
          ) : null}
          <WorkerToolsDropdown
            manifestYaml={manifestYaml}
            onManifestChange={onManifestChange}
            disabled={!canEdit}
            workerId={workerId}
            globalSkills={globalSkills}
            localSkills={localSkills}
          />
        </div>
      </div>

      {loading ? (
        <p className="mt-4 flex items-center gap-2 text-xs text-gov-gray-500 dark:text-dark-muted">
          <Loader2 size={14} className="animate-spin" />
          Cargando capabilities…
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {apiUnavailable && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-[11px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              No se pudo contactar{' '}
              <code className="font-mono">GET /workers/{'{id}'}/capabilities</code>. El dropdown usa
              el manifest en memoria.
            </p>
          )}
          {error && !apiUnavailable && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </p>
          )}

          {payload?.sandbox && (
            <div className="flex flex-wrap gap-2">
              <StatusPill
                ok={payload.sandbox.registered}
                label={payload.sandbox.registered ? 'Sandbox registrado' : 'Sin sandbox'}
              />
              <StatusPill
                ok={payload.sandbox.docker_ok}
                label={payload.sandbox.docker_ok ? 'Docker OK' : 'Docker no disponible'}
                icon={<Container size={12} />}
              />
              {payload.optional?.tavily ? <StatusPill ok label="Tavily activo" /> : null}
              {payload.optional?.browser_sandbox ? (
                <StatusPill ok label="Browser sandbox" />
              ) : null}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function StatusPill({
  ok,
  label,
  icon,
}: {
  ok: boolean;
  label: string;
  icon?: React.ReactNode;
}) {
  return (
    <span
      className={
        ok
          ? 'inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 text-[10px] font-bold text-green-800 dark:bg-green-950/40 dark:text-green-300'
          : 'inline-flex items-center gap-1 rounded-full bg-gov-gray-100 px-2.5 py-1 text-[10px] font-bold text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
      }
    >
      {icon}
      {label}
    </span>
  );
}
