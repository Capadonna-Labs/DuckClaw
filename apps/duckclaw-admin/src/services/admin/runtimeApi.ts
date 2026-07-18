import { adminFetch } from './http';

export const runtimeApi = {
  getRuntimeSettings: (params?: { domains?: string[] }) => {
    const q = new URLSearchParams();
    params?.domains?.forEach((domain) => q.append('domain', domain));
    const qs = q.toString();
    return adminFetch<{
      tenant_id: string;
      actor_email: string;
      settings: {
        setting_id: string;
        tenant_id: string;
        actor_email: string;
        domain: string;
        key: string;
        value_kind: string;
        secret: boolean;
        source: string;
        configured: boolean;
        value_text?: string;
        value_json?: unknown;
        masked_value?: string;
        updated_at: string;
      }[];
    }>(`/settings/runtime${qs ? `?${qs}` : ''}`);
  },
  patchRuntimeSettings: (settings: {
    domain: string;
    key: string;
    value: unknown;
    scope?: 'actor' | 'tenant' | 'global';
    value_kind?: string;
    secret?: boolean;
  }[]) =>
    adminFetch<{ ok: boolean; updated: string[]; task_id?: string; task_ids?: string[] }>(
      '/settings/runtime', {
      method: 'PATCH',
      body: JSON.stringify({ settings }),
    }),
  listVaults: () => adminFetch<{ vaults: { path: string; scope: string }[] }>('/runtime/vaults'),
  getRuntimeConfig: (vaultPath: string, chatId: string) =>
    adminFetch<{
      rows: { key: string; value: string; scope?: string }[];
      warning?: string;
    }>(
      `/runtime/config?vault_path=${encodeURIComponent(vaultPath)}&chat_id=${encodeURIComponent(chatId)}`
    ),
  putRuntimeConfig: (body: {
    vault_path: string;
    chat_id: string;
    key: string;
    value: string;
  }) =>
    adminFetch<{ ok: boolean }>('/runtime/config', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteRuntimeConfig: (vaultPath: string, chatId: string, key: string) =>
    adminFetch<{ ok: boolean }>(
      `/runtime/config?vault_path=${encodeURIComponent(vaultPath)}&chat_id=${encodeURIComponent(chatId)}&key=${encodeURIComponent(key)}`,
      { method: 'DELETE' }
    ),
};
