import { describe, expect, it } from 'vitest';
import {
  applyRoleTemplateToDraft,
  DEFAULT_TOOL_PROFILE,
  WORKER_ROLE_TEMPLATES,
} from './workerRoleTemplates';

describe('workerRoleTemplates', () => {
  it('forces general tool profile when applying role', () => {
    const base = {
      tool_profile: 'minimal' as const,
      skills: ['google_trends'],
      web_search: false,
      browser_sandbox: false,
    };
    const devops = applyRoleTemplateToDraft(base, 'devops');
    expect(devops.tool_profile).toBe(DEFAULT_TOOL_PROFILE);
    expect(devops.web_search).toBe(true);
    expect(devops.browser_sandbox).toBe(true);
    expect(devops.skills).toContain('google_trends');
  });

  it('exposes four role templates for the wizard', () => {
    expect(WORKER_ROLE_TEMPLATES.length).toBe(4);
    expect(WORKER_ROLE_TEMPLATES.map((r) => r.id)).toEqual([
      'general',
      'data_analyst',
      'support',
      'devops',
    ]);
  });
});
