import type {
  ConsoleUser,
  SharedDbGrant,
  WhitelistUser,
} from '@/types/admin';

import { adminFetch } from './http';

export const accessApi = {
  getTelegramRoutes: () =>
    adminFetch<{
      format: string;
      source?: string;
      runtime_key?: string;
      routes: {
        bot: string;
        path: string;
        worker_id?: string;
        tenant_id?: string;
        vault_env_var?: string;
        token_masked?: string;
      }[];
      known_bots?: string[];
      parse_error?: string;
      raw_masked?: string;
      restart_hint?: string;
    }>('/telegram/routes'),
  putTelegramRoutes: (routes: {
    bot: string;
    path: string;
    worker_id: string;
    tenant_id: string;
    vault_env_var?: string;
    token?: string;
  }[]) =>
    adminFetch<{ ok: boolean; updated?: string[]; source?: string; route_count: number; restart_hint?: string }>('/telegram/routes', {
      method: 'PUT',
      body: JSON.stringify({ routes }),
    }),
  getTelegramWhitelist: (tenantId: string) =>
    adminFetch<{
      tenant_id: string;
      effective_tenant_id?: string;
      requested_tenant_id?: string;
      users: WhitelistUser[];
      db_path?: string;
      warning?: string;
      hint?: string;
    }>(`/telegram/whitelist?tenant_id=${encodeURIComponent(tenantId)}`),
  upsertWhitelistUser: (body: {
    tenant_id: string;
    user_id: string;
    username?: string;
    role: string;
  }) =>
    adminFetch<{ ok: boolean }>('/telegram/whitelist', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteWhitelistUser: (tenantId: string, userId: string) =>
    adminFetch<{ ok: boolean }>(
      `/telegram/whitelist?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`,
      { method: 'DELETE' }
    ),
  getAccessOverview: (tenantId: string) =>
    adminFetch<{
      tenant_id: string;
      console_users: number;
      telegram_users: number;
      shared_grants: number;
      db_path?: string;
      db_exists?: boolean;
      persistence_tables?: {
        console: string;
        telegram: string;
        shared: string;
      };
    }>(`/access/overview?tenant_id=${encodeURIComponent(tenantId)}`),
  listConsoleUsers: () =>
    adminFetch<{ users: ConsoleUser[]; db_path?: string; warning?: string }>('/console-users'),
  upsertConsoleUser: (body: {
    email: string;
    nombre: string;
    rol: string;
    password?: string;
    initials?: string;
    active?: boolean;
  }) =>
    adminFetch<{ ok: boolean; user: ConsoleUser }>('/console-users', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchConsoleUser: (
    email: string,
    body: { nombre?: string; rol?: string; password?: string; initials?: string; active?: boolean }
  ) =>
    adminFetch<{ ok: boolean; user: ConsoleUser }>(
      `/console-users?email=${encodeURIComponent(email)}`,
      { method: 'PATCH', body: JSON.stringify(body) }
    ),
  deleteConsoleUser: (email: string) =>
    adminFetch<{ ok: boolean }>(`/console-users?email=${encodeURIComponent(email)}`, {
      method: 'DELETE',
    }),
  listSharedGrants: (tenantId: string) =>
    adminFetch<{ tenant_id: string; grants: SharedDbGrant[]; db_path?: string; warning?: string }>(
      `/access/shared-grants?tenant_id=${encodeURIComponent(tenantId)}`
    ),
  grantSharedAccess: (body: { tenant_id: string; user_id: string; resource_key: string }) =>
    adminFetch<{ ok: boolean }>('/access/shared-grants', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  revokeSharedAccess: (tenantId: string, userId: string, resourceKey: string) =>
    adminFetch<{ ok: boolean }>(
      `/access/shared-grants?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}&resource_key=${encodeURIComponent(resourceKey)}`,
      { method: 'DELETE' }
    ),
};
