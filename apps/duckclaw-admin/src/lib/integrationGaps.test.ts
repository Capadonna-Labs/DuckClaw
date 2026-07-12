import { describe, expect, it } from 'vitest';
import {
  effectiveSkillIdsFromDraft,
  missingIntegrationsForSkills,
} from './integrationGaps';
import type { IntegrationCatalogResponse } from '@/services/adminService';

const catalog: IntegrationCatalogResponse = {
  pack_version: 'test',
  tenant_id: 'default',
  actor_email: 'a@test.local',
  groups: [],
  integrations: [
    {
      id: 'tavily',
      setting_key: 'tavily.api_key',
      domain: 'integrations',
      label: 'Tavily',
      description: '',
      env_fallback: 'TAVILY_API_KEY',
      env_keys: ['TAVILY_API_KEY'],
      related_skills: ['research'],
      default_scope: 'tenant',
      configured: false,
      source: 'default',
    },
    {
      id: 'openweather',
      setting_key: 'openweather.api_key',
      domain: 'integrations',
      label: 'OpenWeather',
      description: '',
      env_fallback: 'OPENWEATHER_API_KEY',
      env_keys: ['OPENWEATHER_API_KEY'],
      related_skills: ['openweather'],
      default_scope: 'tenant',
      configured: true,
      source: 'db',
    },
  ],
};

describe('integrationGaps', () => {
  it('effectiveSkillIdsFromDraft adds research when web_search', () => {
    expect(effectiveSkillIdsFromDraft({ skills: ['reddit'], web_search: true })).toContain('research');
  });

  it('missingIntegrationsForSkills returns unconfigured only', () => {
    const gaps = missingIntegrationsForSkills(catalog, ['research', 'openweather']);
    expect(gaps).toHaveLength(1);
    expect(gaps[0]?.integration.id).toBe('tavily');
    expect(gaps[0]?.skill).toBe('research');
  });
});
