'use client';

import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { useAuthStore } from '@/store/authStore';

const AuthHydrationContext = createContext(false);

export function AuthProvider({ children }: { children: ReactNode }) {
  const hydrated = useRef(false);
  const { setUser, setLoading, setHasHydrated } = useAuthStore();

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;

    fetch('/api/admin/auth/me', { credentials: 'include', cache: 'no-store' })
      .then(async (res) => {
        if (!res.ok) {
          setUser(null);
          return;
        }
        const data = (await res.json()) as { user?: Parameters<typeof setUser>[0] };
        setUser(data.user ?? null);
      })
      .catch(() => setUser(null))
      .finally(() => {
        setLoading(false);
        setHasHydrated(true);
      });
  }, [setUser, setLoading, setHasHydrated]);

  return (
    <AuthHydrationContext.Provider value={true}>{children}</AuthHydrationContext.Provider>
  );
}

export function useAuthHydrated(): boolean {
  return useContext(AuthHydrationContext);
}
