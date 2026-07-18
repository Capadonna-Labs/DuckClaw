import type {
  RestoreFrameworkPoliciesResponse,
  SyncCatalogPromptsResponse,
} from '@/types/admin';

import { adminFetch } from './http';

export interface PromptPolicy {
  policy_id: string;
  policy_type: string;
  policy_name: string;
  version: number;
  status: string;
  content: string;
  checksum: string;
  metadata?: Record<string, unknown>;
  active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PromptPolicyRequirement {
  policy_type: string;
  policy_name: string;
  source: string;
}

export interface PromptPolicyHealth {
  ok: boolean;
  checked_count: number;
  missing_count: number;
  inherited_count: number;
  requirements: PromptPolicyRequirement[];
  missing: PromptPolicyRequirement[];
  inherited: Array<PromptPolicyRequirement & { warning: string }>;
}

export interface PromptPolicyUpsertInput {
  policy_type: string;
  policy_name: string;
  version: number;
  status?: string;
  content: string;
  metadata?: Record<string, unknown>;
}

function promptPoliciesQueryString(params?: {
  policy_type?: string;
  policy_name?: string;
  include_inactive?: boolean;
}): string {
  const qs = new URLSearchParams();
  if (params?.policy_type) qs.set('policy_type', params.policy_type);
  if (params?.policy_name) qs.set('policy_name', params.policy_name);
  if (params?.include_inactive) qs.set('include_inactive', 'true');
  const suffix = qs.toString();
  return suffix ? `?${suffix}` : '';
}

export const policiesApi = {
  listPromptPolicies: (params?: {
    policy_type?: string;
    policy_name?: string;
    include_inactive?: boolean;
  }) =>
    adminFetch<{ policies: PromptPolicy[] }>(`/prompt-policies${promptPoliciesQueryString(params)}`).then(
      (r) => r.policies
    ),
  upsertPromptPolicy: (body: PromptPolicyUpsertInput) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      policy: {
        policy_id: string;
        policy_type: string;
        policy_name: string;
        version: number;
        status: string;
        active: boolean;
      };
    }>('/prompt-policies', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deactivatePromptPolicy: (policyType: string, policyName: string, version: number) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      policy_type: string;
      policy_name: string;
      version: number;
    }>(
      `/prompt-policies/${encodeURIComponent(policyType)}/${encodeURIComponent(policyName)}?version=${encodeURIComponent(String(version))}`,
      { method: 'DELETE' }
    ),
  getPromptPolicyHealth: () => adminFetch<PromptPolicyHealth>('/prompt-policies/health'),
  restoreFrameworkPolicies: () =>
    adminFetch<RestoreFrameworkPoliciesResponse>('/prompt-policies/restore-framework', {
      method: 'POST',
    }),
  syncCatalogPrompts: (force = false) =>
    adminFetch<SyncCatalogPromptsResponse>(
      `/prompt-policies/sync-catalog?force=${force ? 'true' : 'false'}`,
      { method: 'POST' }
    ),
};
