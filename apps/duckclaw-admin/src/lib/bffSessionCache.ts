/**
 * In-memory BFF session cache — avoids N× GET /auth/me per parallel admin API burst.
 * Server-only (Next.js route handlers).
 */

import type { SessionUser } from '@/lib/authProxy';

export const BFF_SESSION_COOKIE = 'session';
export const BFF_SESSION_TTL_MS = 120_000;
/** Tras timeout del gateway, aceptar sesión ya validada durante este margen. */
export const BFF_SESSION_STALE_GRACE_MS = 10 * 60_000;

type CacheEntry = {
  user: SessionUser;
  expiresAt: number;
  lastGoodAt: number;
};

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<SessionUser | null>>();

export function bffSessionKeyFromCookie(sessionCookie: string | null | undefined): string | null {
  const key = (sessionCookie || '').trim();
  return key || null;
}

export function getCachedBffSession(
  key: string,
  opts?: { allowStale?: boolean }
): SessionUser | null | undefined {
  const entry = cache.get(key);
  if (!entry) return undefined;
  const now = Date.now();
  if (now <= entry.expiresAt) return entry.user;
  if (opts?.allowStale && now <= entry.lastGoodAt + BFF_SESSION_STALE_GRACE_MS) {
    return entry.user;
  }
  cache.delete(key);
  return undefined;
}

export function setCachedBffSession(key: string, user: SessionUser): void {
  const now = Date.now();
  cache.set(key, {
    user,
    expiresAt: now + BFF_SESSION_TTL_MS,
    lastGoodAt: now,
  });
}

export function invalidateBffSessionCache(key?: string | null): void {
  if (key) {
    cache.delete(key);
    inflight.delete(key);
    return;
  }
  cache.clear();
  inflight.clear();
}

export function coalesceBffSessionLookup(
  key: string,
  loader: () => Promise<SessionUser | null>
): Promise<SessionUser | null> {
  const pending = inflight.get(key);
  if (pending) return pending;
  const promise = loader().finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, promise);
  return promise;
}

/** Test helper */
export function resetBffSessionCacheForTests(): void {
  invalidateBffSessionCache();
}
