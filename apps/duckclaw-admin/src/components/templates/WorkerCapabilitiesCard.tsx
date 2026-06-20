'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Blocks, Container, Loader2, Wrench } from 'lucide-react';
import { adminService, type WorkerCapabilities } from '@/services/adminService';

function skillsFromManifestYaml(yamlText: string): string[] {
  const lines = yamlText.split('\n');
  const skills: string[] = [];
  let inSkills = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (/^skills:\s*$/.test(line)) {
      inSkills = true;
      continue;
    }
    if (inSkills) {
      if (/^-\s+/.test(line)) {
        skills.push(line.replace(/^-\s+/, '').replace(/^['"]|['"]$/g, '').trim());
        continue;
      }
      if (line && !line.startsWith('#') && !/^-\s+/.test(line)) {
        inSkills = false;
      }
    }
  }
  return skills.filter(Boolean);
}

type WorkerCapabilitiesCardProps = {
  workerId: string;
  manifestYaml?: string;
};

export function WorkerCapabilitiesCard({
  workerId,
  manifestYaml,
}: WorkerCapabilitiesCardProps) {
  const [payload, setPayload] = useState<WorkerCapabilities | null>(null);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, [load]);

  const effectiveSkills = useMemo(() => {
    if (payload?.skills_effective?.length) return payload.skills_effective;
    if (manifestYaml?.trim()) return skillsFromManifestYaml(manifestYaml);
    return [];
  }, [payload?.skills_effective, manifestYaml]);

  const declaredSkills = payload?.skills_declared ?? [];

  return (
    <section className="rounded-2xl border border-gov-gray-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
            <Wrench size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
            Capabilities del worker
          </p>
          <p className="mt-1 text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Skills efectivas, tools en runtime y estado del sandbox.
          </p>
        </div>
        {payload?.framework_baseline && (
          <span className="shrink-0 rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-black uppercase text-green-800 dark:bg-green-950/40 dark:text-green-300">
            baseline
          </span>
        )}
      </div>

      {loading ? (
        <p className="mt-4 flex items-center gap-2 text-xs text-gov-gray-500 dark:text-dark-muted">
          <Loader2 size={14} className="animate-spin" />
          Cargando capabilities…
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {apiUnavailable && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-[11px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              No se pudo contactar{' '}
              <code className="font-mono">GET /workers/{'{id}'}/capabilities</code>. Mostrando
              skills del manifest local.
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
              {payload.optional?.tavily && (
                <StatusPill ok label="Tavily activo" />
              )}
              {payload.optional?.browser_sandbox && (
                <StatusPill ok label="Browser sandbox" />
              )}
            </div>
          )}

          {declaredSkills.length > 0 && declaredSkills.length !== effectiveSkills.length && (
            <CapabilityGroup
              title="Skills declaradas (manifest)"
              items={declaredSkills.map((name) => ({ key: name, label: name }))}
            />
          )}

          <CapabilityGroup
            title="Skills efectivas"
            emptyHint="Sin skills efectivas."
            items={effectiveSkills.map((name) => ({ key: name, label: name }))}
          />

          {(payload?.tools_runtime?.length ?? 0) > 0 && (
            <CapabilityGroup
              title="Tools en runtime"
              items={(payload?.tools_runtime ?? []).map((name) => ({
                key: name,
                label: name,
              }))}
            />
          )}

          {(payload?.gaps?.length ?? 0) > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/20">
              <p className="flex items-center gap-1.5 text-[10px] font-black uppercase text-amber-900 dark:text-amber-200">
                <AlertTriangle size={12} />
                Gaps detectados
              </p>
              <ul className="mt-1.5 list-inside list-disc text-[11px] text-amber-900 dark:text-amber-100">
                {payload?.gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
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

function CapabilityGroup({
  title,
  emptyHint,
  items,
}: {
  title: string;
  emptyHint?: string;
  items: { key: string; label: string; hint?: string }[];
}) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        <Blocks size={12} />
        {title}
      </p>
      {items.length === 0 ? (
        emptyHint ? (
          <p className="mt-2 text-[11px] text-gov-gray-400 dark:text-dark-muted">{emptyHint}</p>
        ) : null
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {items.map((item) => (
            <span
              key={item.key}
              title={item.hint}
              className="rounded-full bg-gov-gray-50 px-2.5 py-1 text-[10px] font-bold text-gov-gray-700 dark:bg-dark-bg dark:text-dark-muted"
            >
              <span className="font-mono">{item.label}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
