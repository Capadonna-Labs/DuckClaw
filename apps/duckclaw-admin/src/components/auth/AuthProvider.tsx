'use client';

import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useAuthStore } from '@/store/authStore';

const AuthHydrationContext = createContext(false);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { setUser, setHasHydrated } = useAuthStore();

  useEffect(() => {
    let active = true;

    fetch('/api/admin/auth/me', { credentials: 'include', cache: 'no-store' })
      .then(async (res) => {
        if (!active || !res.ok) {
          if (active) setUser(null);
          return;
        }
        const data = (await res.json()) as { user?: Parameters<typeof setUser>[0] };
        if (active) setUser(data.user ?? null);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setHasHydrated(true);
      });

    return () => {
      active = false;
    };
  }, [setUser, setHasHydrated]);

  return (
    <AuthHydrationContext.Provider value={true}>{children}</AuthHydrationContext.Provider>
  );
}

export function useAuthHydrated(): boolean {
  return useContext(AuthHydrationContext);
}
