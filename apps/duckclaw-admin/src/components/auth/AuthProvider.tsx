'use client';

import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from 'react';
import { useAuthStore } from '@/store/authStore';
import type { AdminUser } from '@/types/admin';
import { normalizeAdminRole } from '@/lib/roles';
import {
  AUTH_ME_TIMEOUT_MS,
  fetchAuthMeWithTimeout,
  readAuthSnapshot,
  writeAuthSnapshot,
} from '@/lib/authSessionCache';
import { redirectToLoginOnUnauthorized } from '@/lib/sessionExpired';

const AuthHydrationContext = createContext(false);

function parseSessionUser(raw: Record<string, unknown> | undefined | null): AdminUser | null {
  if (!raw?.email) return null;
  const profileRaw = raw.profile;
  const tenantId =
    profileRaw &&
    typeof profileRaw === 'object' &&
    typeof (profileRaw as Record<string, unknown>).tenant_id === 'string'
      ? String((profileRaw as Record<string, unknown>).tenant_id).trim()
      : '';
  return {
    id: String(raw.id ?? `user-${raw.email}`),
    email: String(raw.email),
    nombre: String(raw.nombre ?? raw.email),
    rol: normalizeAdminRole(raw.rol),
    initials: String(raw.initials ?? String(raw.email).slice(0, 2).toUpperCase()),
    profile: tenantId ? { tenant_id: tenantId } : undefined,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { setUser, setHasHydrated, setAuthError } = useAuthStore();
  const runId = useRef(0);

  const hydrateSession = useCallback(async () => {
    const id = ++runId.current;
    setAuthError(null);

    const cached = readAuthSnapshot();
    if (cached) {
      setUser(cached);
      setHasHydrated(true);
    }

    try {
      const res = await fetchAuthMeWithTimeout(AUTH_ME_TIMEOUT_MS);
      if (id !== runId.current) return;

      if (!res.ok) {
        const live = useAuthStore.getState();
        // Stale /me (started before Entrar) must not wipe a login that already succeeded.
        if (live.isSubmitting || live.isAuthenticated) {
          return;
        }
        setUser(null);
        writeAuthSnapshot(null);
        if (res.status === 503) {
          setAuthError('Gateway no disponible. Revisa que duckops up haya terminado.');
        } else if (res.status === 401) {
          setAuthError(null);
          redirectToLoginOnUnauthorized();
        } else {
          setAuthError(`No se pudo validar la sesión (${res.status}).`);
        }
        return;
      }

      const data = (await res.json()) as { user?: Record<string, unknown> };
      const user = parseSessionUser(data.user);
      setUser(user);
      writeAuthSnapshot(user);
      setAuthError(null);
    } catch (err) {
      if (id !== runId.current) return;
      const timedOut = err instanceof DOMException && err.name === 'AbortError';
      const live = useAuthStore.getState();
      if (live.isSubmitting || live.isAuthenticated) {
        return;
      }
      if (!cached) {
        setUser(null);
        writeAuthSnapshot(null);
      }
      setAuthError(
        timedOut
          ? `El gateway no respondió en ${AUTH_ME_TIMEOUT_MS / 1000}s. Comprueba http://127.0.0.1:8000/health y reinicia duckops up.`
          : 'No se pudo contactar con el servidor de sesión.'
      );
    } finally {
      if (id === runId.current) {
        setHasHydrated(true);
      }
    }
  }, [setAuthError, setHasHydrated, setUser]);

  useEffect(() => {
    void hydrateSession();
    return () => {
      runId.current += 1;
    };
  }, [hydrateSession]);

  return (
    <AuthHydrationContext.Provider value={true}>{children}</AuthHydrationContext.Provider>
  );
}

export function useAuthHydrated(): boolean {
  return useContext(AuthHydrationContext);
}
