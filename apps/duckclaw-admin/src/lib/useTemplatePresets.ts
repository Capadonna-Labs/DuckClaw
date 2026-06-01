'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { TemplatePreset } from '@/lib/templatePresets';

function iconLabelFor(_id?: string): string {
  void _id;
  return '';
}

function buildPresetsFromCatalog(
  industries: { id: string; name: string; path: string; subtitle?: string }[],
  starters: { id: string; name: string; path: string; subtitle?: string }[],
  templates: { id: string; name?: string }[]
): TemplatePreset[] {
  const seen = new Set<string>();
  const out: TemplatePreset[] = [];

  const push = (id: string, title: string, subtitle: string, recommended?: boolean) => {
    const key = id.trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push({
      id: key,
      title,
      subtitle,
      emoji: iconLabelFor(key),
      recommended,
    });
  };

  for (const s of starters) {
    push(
      s.path || s.id,
      s.name,
      s.subtitle ?? `Plantilla ${s.path || s.id}`,
      (s.path || s.id) === 'default'
    );
  }

  for (const ind of industries) {
    push(ind.path || ind.id, ind.name, `Industria: ${ind.path || ind.id}`);
  }

  for (const t of templates) {
    const id = t.id;
    if (id === 'default') continue;
    push(id, t.name ?? id, `Worker en forge/templates/${id}`);
  }

  return out;
}

export function useTemplatePresets(advancedMode: boolean) {
  const [presets, setPresets] = useState<TemplatePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([adminService.getIndustriesCatalog(), adminService.listTemplates()])
      .then(([catalog, templates]) => {
        if (cancelled) return;
        const base = buildPresetsFromCatalog(
          catalog.industries ?? [],
          catalog.starters ?? [],
          templates.map((t) => ({ id: t.id, name: t.name }))
        );
        if (advancedMode) {
          const extra = templates
            .filter((t) => !base.some((p) => p.id === t.id))
            .map((t) => ({
              id: t.id,
              title: t.name ?? t.id,
              subtitle: `Worker ${t.id}`,
              emoji: iconLabelFor(t.id),
            }));
          setPresets([...base, ...extra]);
        } else {
          setPresets(base);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'No se pudo cargar catálogo');
          setPresets([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [advancedMode]);

  return { presets, loading, error };
}
