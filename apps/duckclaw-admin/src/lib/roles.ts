import type { AdminRole } from '@/types/admin';

export type ConsoleRole = 'admin' | 'user';

export function normalizeAdminRole(role: unknown): ConsoleRole {
  return role === 'admin' ? 'admin' : 'user';
}

export function isAdminRole(role: AdminRole | null | undefined): boolean {
  return normalizeAdminRole(role) === 'admin';
}

export function isUserRole(role: AdminRole | null | undefined): boolean {
  return normalizeAdminRole(role) === 'user';
}

export function canCreateAgents(role: AdminRole | null | undefined): boolean {
  const normalized = normalizeAdminRole(role);
  return normalized === 'admin' || normalized === 'user';
}

export function consoleRoleLabel(role: AdminRole | null | undefined): string {
  return isAdminRole(role) ? 'Admin Console' : 'User Console';
}

export function roleDisplayName(role: AdminRole | null | undefined): string {
  return isAdminRole(role) ? 'admin' : 'user';
}
