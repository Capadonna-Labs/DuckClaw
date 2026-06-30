'use client';

import { useEffect, useState } from 'react';
import { adminService, type SkillCategoryPayload } from '@/services/adminService';
import type { ToolProfile } from '@/lib/manifestQuickEdit';
import type { SkillCategory } from '@/lib/skillCategories';

function mapApiCategory(category: SkillCategoryPayload): SkillCategory {
  return {
    id: category.id,
    title: category.title,
    description: category.description ?? undefined,
    // El picker siempre permite activar/desactivar skills de plataforma vía manifest.
    readOnly: false,
    skills: (category.skills ?? []).map((skill) => ({
      id: skill.id,
      label: skill.label || skill.id,
      hint: skill.hint ?? undefined,
    })),
  };
}

export function useSkillCategoriesCatalog() {
  const [platformCategories, setPlatformCategories] = useState<SkillCategory[]>([]);
  const [baselineProfiles, setBaselineProfiles] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminService
      .getSkillCategories()
      .then((payload) => {
        if (cancelled) return;
        setPlatformCategories((payload.categories ?? []).map(mapApiCategory));
        setBaselineProfiles(payload.baseline_profiles ?? {});
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setPlatformCategories([]);
        setBaselineProfiles({});
        setError(e instanceof Error ? e.message : 'No se pudieron cargar categorías');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    platformCategories,
    baselineProfiles,
    loading,
    error,
  };
}

export function baselineSkillsForProfileFromCatalog(
  profiles: Record<string, string[]>,
  profile: ToolProfile
): string[] {
  return profiles[profile] ?? profiles.general ?? [];
}
