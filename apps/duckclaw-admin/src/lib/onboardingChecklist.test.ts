import { describe, expect, it } from 'vitest';
import {
  buildOnboardingChecklistSteps,
  integrationsStepDetail,
  isIntegrationsOnboardingOk,
  skillIdsFromManifestYaml,
} from './onboardingChecklist';
import type { IntegrationCatalogResponse } from '@/services/adminService';

const catalog: IntegrationCatalogResponse = {
  pack_version: 'test',
  tenant_id: 'default',
  actor_email: 'a@test.local',
  groups: [
    {
      id: 'llm_inference',
      title: 'LLM',
      description: '',
      sort_order: 0,
      integrations: [
        {
          id: 'deepseek',
          setting_key: 'deepseek.api_key',
          domain: 'integrations',
          label: 'DeepSeek',
          description: '',
          env_fallback: 'DEEPSEEK_API_KEY',
          env_keys: ['DEEPSEEK_API_KEY'],
          related_skills: [],
          default_scope: 'tenant',
          configured: false,
          source: 'default',
        },
      ],
    },
  ],
  integrations: [],
};

describe('onboardingChecklist', () => {
  it('skillIdsFromManifestYaml collects manifest skills', () => {
    const yaml = `
skills:
  - research
  - openweather
  - reddit
`;
    expect(skillIdsFromManifestYaml(yaml)).toEqual(
      expect.arrayContaining(['research', 'openweather', 'reddit'])
    );
  });

  it('isIntegrationsOnboardingOk requires no llm gap', () => {
    expect(isIntegrationsOnboardingOk(null)).toBe(true);
    expect(isIntegrationsOnboardingOk({ message: 'falta clave' })).toBe(false);
  });

  it('integrationsStepDetail prefers llm gap message', () => {
    expect(integrationsStepDetail({ message: 'Falta DeepSeek' }, catalog)).toContain('DeepSeek');
  });

  it('buildOnboardingChecklistSteps hides when agent and llm ready', () => {
    expect(
      buildOnboardingChecklistSteps({
        agentOk: true,
        agentDetail: '1 agente',
        llmGap: null,
        catalog,
        knowledgeOk: false,
        knowledgeDetail: 'sin fuentes',
      })
    ).toBeNull();
  });

  it('buildOnboardingChecklistSteps keeps integrations pending without llm key', () => {
    const steps = buildOnboardingChecklistSteps({
      agentOk: true,
      agentDetail: '1 agente',
      llmGap: { message: 'Falta API key', label: 'DeepSeek' },
      catalog,
      knowledgeOk: false,
      knowledgeDetail: 'sin fuentes',
    });
    expect(steps).not.toBeNull();
    expect(steps?.find((s) => s.id === 'integrations')?.state).toBe('pending');
  });
});
