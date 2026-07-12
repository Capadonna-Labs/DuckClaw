import { parseManifestSkills } from '@/lib/manifestSkillsEdit';
import { normalizeSkillId } from '@/lib/skillCategories';
import type { IntegrationCatalogResponse } from '@/services/adminService';

export type OnboardingChecklistStepId = 'agent' | 'integrations' | 'knowledge';

export type OnboardingChecklistStep = {
  id: OnboardingChecklistStepId;
  title: string;
  detail: string;
  state: 'pending' | 'ok';
  href: string;
  cta: string;
  optional?: boolean;
};

export type LlmGapLike = {
  message?: string;
  label?: string;
} | null | undefined;

/** Skill ids activos en manifest (opcionales + declarados). */
export function skillIdsFromManifestYaml(manifestYaml: string): string[] {
  const parsed = parseManifestSkills(manifestYaml);
  const ids = new Set<string>();
  for (const name of [...parsed.skillNames, ...parsed.optionalSkillNames]) {
    const id = normalizeSkillId(name);
    if (id) ids.add(id);
  }
  return [...ids];
}

export function llmInferenceConfiguredCount(catalog: IntegrationCatalogResponse | null): {
  configured: number;
  total: number;
} {
  const group = catalog?.groups?.find((item) => item.id === 'llm_inference');
  const items = group?.integrations ?? [];
  const configured = items.filter((item) => item.configured).length;
  return { configured, total: items.length };
}

export function integrationsStepDetail(
  llmGap: LlmGapLike,
  catalog: IntegrationCatalogResponse | null
): string {
  if (llmGap?.message) {
    return llmGap.message;
  }
  const { configured, total } = llmInferenceConfiguredCount(catalog);
  if (total > 0 && configured === 0) {
    return 'Configura al menos la API key del proveedor LLM activo (grupo LLM e inferencia).';
  }
  if (total > 0) {
    return `${configured}/${total} proveedores LLM con clave · Tavily y otras APIs son opcionales hasta activar skills.`;
  }
  return 'API keys de LLM e integraciones opcionales (Tavily, OpenWeather, …).';
}

export function isIntegrationsOnboardingOk(llmGap: LlmGapLike): boolean {
  return !llmGap?.message;
}

export function buildOnboardingChecklistSteps(params: {
  agentOk: boolean;
  agentDetail: string;
  llmGap: LlmGapLike;
  catalog: IntegrationCatalogResponse | null;
  knowledgeOk: boolean;
  knowledgeDetail: string;
}): OnboardingChecklistStep[] | null {
  const integrationsOk = isIntegrationsOnboardingOk(params.llmGap);
  if (params.agentOk && integrationsOk) {
    return null;
  }

  return [
    {
      id: 'agent',
      title: 'Crear un agente',
      detail: params.agentDetail,
      state: params.agentOk ? 'ok' : 'pending',
      href: '/templates',
      cta: params.agentOk ? 'Ver plantillas' : 'Abrir wizard',
    },
    {
      id: 'integrations',
      title: 'Integraciones y LLM',
      detail: integrationsStepDetail(params.llmGap, params.catalog),
      state: integrationsOk ? 'ok' : 'pending',
      href: '/integraciones?tab=keys',
      cta: integrationsOk ? 'Gestionar' : 'Configurar claves',
    },
    {
      id: 'knowledge',
      title: 'Conocimiento',
      detail: params.knowledgeDetail,
      state: params.knowledgeOk ? 'ok' : 'pending',
      href: '/knowledge',
      cta: params.knowledgeOk ? 'Gestionar' : 'Importar (opcional)',
      optional: true,
    },
  ];
}

export function isPrimaryChecklistCta(
  step: OnboardingChecklistStep,
  steps: OnboardingChecklistStep[]
): boolean {
  if (step.state === 'ok' || step.optional) return false;
  const firstPending = steps.find((item) => item.state !== 'ok' && !item.optional);
  return firstPending?.id === step.id;
}
