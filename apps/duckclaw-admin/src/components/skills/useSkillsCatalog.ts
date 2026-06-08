'use client';

import { useEffect, useState } from 'react';
import { adminService, type SkillCatalogItem } from '@/services/adminService';

export const EMPTY_SKILL_FORM = {
  name: '',
  description: '',
  skillType: 'python',
  implementationRef: '',
};

export type SkillFormState = typeof EMPTY_SKILL_FORM;

export function useSkillsCatalog() {
  const [globalSkills, setGlobalSkills] = useState<SkillCatalogItem[]>([]);
  const [localSkills, setLocalSkills] = useState<SkillCatalogItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadSkills = () =>
    adminService.getSkillsCatalog().then((r) => {
      setGlobalSkills(r.global ?? []);
      setLocalSkills(r.template_local ?? []);
    });

  useEffect(() => {
    loadSkills().catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  return {
    globalSkills,
    localSkills,
    error,
    setError,
    loadSkills,
  };
}

export function defaultImplementationRef(name: string) {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9_.-]+/g, '_');
  return slug ? `db://skills/${slug}.py` : '';
}

export function filterSkills(items: SkillCatalogItem[], q: string) {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter(
    (skill) =>
      skill.id.toLowerCase().includes(needle) ||
      skill.path.toLowerCase().includes(needle) ||
      (skill.worker_id ?? '').toLowerCase().includes(needle)
  );
}
