'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, Loader2, Plus, Wrench } from 'lucide-react';
import { adminService, type UserAgentDraft } from '@/services/adminService';
import { useSkillCategoriesCatalog } from '@/components/skills/useSkillCategoriesCatalog';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';
import { IntegrationSecretsBanner } from '@/components/integrations/IntegrationSecretsBanner';
import { useIntegrationCatalog } from '@/components/integrations/useIntegrationCatalog';
import {
  buildCatalogSkillCreateBody,
  catalogSkillNamesFromLists,
  collectPlatformSkillIds,
  mergeSkillIntoDraft,
  resolveSuggestedSkillInstall,
  type SuggestedSkillRow,
} from '@/lib/suggestedSkillInstall';
import { effectiveSkillIdsFromDraft, missingIntegrationsForSkills } from '@/lib/integrationGaps';
import { pollWriteTask } from '@/lib/pollWriteTask';

type SuggestedSkillsInstallPanelProps = {
  draft: UserAgentDraft;
  onDraftChange: (patch: Partial<UserAgentDraft>) => void;
  disabled?: boolean;
};

function platformIdsFromCategories(
  categories: { skills: { id: string }[] }[]
): string[] {
  return categories.flatMap((category) => category.skills.map((skill) => skill.id));
}

export function SuggestedSkillsInstallPanel({
  draft,
  onDraftChange,
  disabled,
}: SuggestedSkillsInstallPanelProps) {
  const { globalSkills, localSkills, loadSkills } = useSkillsCatalog();
  const { platformCategories } = useSkillCategoriesCatalog();
  const { catalog } = useIntegrationCatalog();
  const [busySkill, setBusySkill] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const platformSkillIds = useMemo(
    () => collectPlatformSkillIds(platformIdsFromCategories(platformCategories)),
    [platformCategories]
  );
  const catalogSkillNames = useMemo(
    () => catalogSkillNamesFromLists(globalSkills, localSkills),
    [globalSkills, localSkills]
  );

  const integrationGaps = useMemo(
    () =>
      missingIntegrationsForSkills(
        catalog,
        effectiveSkillIdsFromDraft({
          skills: draft.skills ?? [],
          web_search: draft.web_search,
        })
      ),
    [catalog, draft.skills, draft.web_search]
  );

  const rows = draft.suggested_skills ?? [];
  if (rows.length === 0 && integrationGaps.length === 0) return null;

  const activateInDraft = (skillName: string) => {
    onDraftChange({ skills: mergeSkillIntoDraft(draft.skills, skillName) });
    setNotice(`Skill «${skillName}» añadida al manifest del agente.`);
    setError(null);
  };

  const registerInCatalog = async (skill: SuggestedSkillRow) => {
    if (disabled || busySkill) return;
    setBusySkill(skill.name);
    setError(null);
    setNotice(null);
    try {
      const body = buildCatalogSkillCreateBody(skill);
      const result = await adminService.createSkill(body);
      if (result.task_id) {
        const polled = await pollWriteTask(result.task_id);
        if (polled.state === 'failed') {
          throw new Error(polled.detail || 'No se registró la skill en DuckDB');
        }
      }
      await loadSkills();
      activateInDraft(skill.name);
      setNotice(
        `«${skill.name}» registrada en catálogo y añadida al agente. Falta implementar ${body.implementation_ref}.`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar la skill');
    } finally {
      setBusySkill(null);
    }
  };

  return (
    <section className="rounded-lg border border-gov-gray-200 bg-white p-3 dark:border-dark-border dark:bg-dark-surface">
      <p className="flex items-center gap-2 text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
        <Wrench size={14} className="text-gov-blue-700 dark:text-dark-cyan" />
        Skills sugeridas por la IA
      </p>
      <p className="mt-1 text-[10px] text-gov-gray-500 dark:text-dark-muted">
        Plataforma: activar en manifest. Custom: registro en catálogo + bridge Python. API keys en
        Integraciones.
      </p>

      <IntegrationSecretsBanner gaps={integrationGaps} compact className="mt-3" />

      {notice ? (
        <p className="mt-2 rounded-lg bg-emerald-50 px-2 py-1.5 text-[10px] text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 rounded-lg bg-red-50 px-2 py-1.5 text-[10px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      ) : null}

      {rows.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {rows.map((skill) => {
            const kind = resolveSuggestedSkillInstall({
              skill,
              draftSkills: draft.skills,
              platformSkillIds,
              catalogSkillNames,
            });
            const busy = busySkill === skill.name;

            return (
              <li
                key={skill.name}
                className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-gov-gray-100 px-2 py-2 dark:border-dark-border"
              >
                <div className="min-w-0">
                  <p className="font-mono text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
                    {skill.name}
                  </p>
                  <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted">{skill.reason}</p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                  {kind === 'activated' ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                      <CheckCircle2 size={12} />
                      En el agente
                    </span>
                  ) : null}
                  {kind === 'platform' || kind === 'catalog' ? (
                    <button
                      type="button"
                      disabled={disabled || busy}
                      onClick={() => activateInDraft(skill.name)}
                      className="inline-flex items-center gap-1 rounded-lg bg-gov-blue-700 px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={10} className="animate-spin" /> : <Plus size={10} />}
                      Activar
                    </button>
                  ) : null}
                  {kind === 'custom' ? (
                    <>
                      <button
                        type="button"
                        disabled={disabled || busy}
                        onClick={() => void registerInCatalog(skill)}
                        className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-[10px] font-semibold dark:border-dark-border disabled:opacity-50"
                      >
                        {busy ? <Loader2 size={10} className="animate-spin" /> : null}
                        Registrar
                      </button>
                      <Link
                        href={`/plataforma?tab=skills&skillsTab=catalog`}
                        className="text-[10px] font-semibold text-gov-blue-700 hover:underline dark:text-dark-cyan"
                      >
                        Implementar
                      </Link>
                    </>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
