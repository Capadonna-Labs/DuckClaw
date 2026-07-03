import type { AdminUser } from '@/types/admin';

const STORAGE_KEY = 'duckclaw:auth:snapshot:v1';

export function readAuthSnapshot(): AdminUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AdminUser;
    if (!parsed?.email) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeAuthSnapshot(user: AdminUser | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (!user) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  } catch {
    /* quota / private mode */
  }
}

export const AUTH_ME_TIMEOUT_MS = 8_000;

export async function fetchAuthMeWithTimeout(timeoutMs = AUTH_ME_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch('/api/admin/auth/me', {
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}
