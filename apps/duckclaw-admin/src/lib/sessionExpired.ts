/** Session expiry: clear local auth and send the user to login. */

import { writeAuthSnapshot } from '@/lib/authSessionCache';
import { useAuthStore } from '@/store/authStore';

let redirecting = false;

export function isUnauthorizedStatus(status: number): boolean {
  return status === 401;
}

export function isUnauthorizedDetail(detail: string | null | undefined): boolean {
  const m = (detail || '').trim().toLowerCase();
  return m === 'no autenticado' || m.includes('no autenticado') || m.includes('unauthorized');
}

/**
 * Clears cached auth and navigates to /login.
 * Safe to call from fetch helpers (outside React). Idempotent.
 */
export function redirectToLoginOnUnauthorized(returnPath?: string): void {
  if (typeof window === 'undefined') return;
  writeAuthSnapshot(null);
  try {
    useAuthStore.getState().setUser(null);
    useAuthStore.getState().setAuthError(null);
    const path = returnPath || window.location.pathname;
    if (path && path !== '/login' && !path.startsWith('/login')) {
      useAuthStore.getState().setReturnTo(path);
    }
  } catch {
    /* store unavailable during SSR / early boot */
  }
  if (redirecting) return;
  const path = window.location.pathname || '';
  if (path === '/login' || path.startsWith('/login')) return;
  redirecting = true;
  window.location.assign('/login');
}
