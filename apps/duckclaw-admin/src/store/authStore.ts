import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AdminRole, AdminUser } from '@/types/admin';

interface AuthState {
  usuario: AdminUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginError: string | null;
  returnTo: string | null;
  hasHydrated: boolean;

  loginWithCredentials: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setReturnTo: (path: string | null) => void;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      usuario: null,
      isAuthenticated: false,
      isLoading: false,
      loginError: null,
      returnTo: null,
      hasHydrated: false,

      setReturnTo: (path) => set({ returnTo: path }),
      setHasHydrated: (value) => set({ hasHydrated: value }),

      loginWithCredentials: async (email, password) => {
        set({ isLoading: true, loginError: null });
        try {
          const res = await fetch('/api/admin/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email.trim(), password }),
            cache: 'no-store',
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            const detail =
              typeof data?.detail === 'string'
                ? data.detail
                : data?.detail?.detail ?? data?.title ?? 'Credenciales inválidas';
            set({ isLoading: false, loginError: detail });
            return;
          }
          const user: AdminUser = {
            id: String(data.id ?? `user-${data.email}`),
            email: String(data.email),
            nombre: String(data.nombre ?? data.email),
            rol: (data.rol === 'admin' ? 'admin' : 'viewer') as AdminRole,
            initials: String(data.initials ?? data.email.slice(0, 2).toUpperCase()),
          };
          set({
            usuario: user,
            isAuthenticated: true,
            isLoading: false,
            loginError: null,
          });
        } catch {
          set({ isLoading: false, loginError: 'No se pudo conectar con el servidor' });
        }
      },

      logout: () => {
        set({
          usuario: null,
          isAuthenticated: false,
          isLoading: false,
          loginError: null,
          returnTo: null,
        });
      },
    }),
    {
      name: 'duckclaw-admin-auth',
      partialize: (state) => ({
        usuario: state.usuario,
        isAuthenticated: state.isAuthenticated,
        returnTo: state.returnTo,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);

/** Post-login / post-auth-guard destination; falls back to overview. */
export function adminPostAuthPath(returnTo: string | null | undefined): string {
  if (returnTo && returnTo.startsWith('/') && returnTo !== '/login') {
    return returnTo;
  }
  return '/overview';
}

export function authHeadersForBff(rol: AdminRole | undefined): HeadersInit {
  return { 'x-duckclaw-role': rol ?? 'viewer' };
}
