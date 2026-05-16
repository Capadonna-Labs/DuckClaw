import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AdminRole, AdminUser } from '@/types/admin';
import { ADMIN_USERS } from '@/config/adminUsers';

interface AuthState {
  usuario: AdminUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginError: string | null;
  returnTo: string | null;

  loginWithCredentials: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setReturnTo: (path: string | null) => void;
}

const USER_MAP = Object.fromEntries(
  ADMIN_USERS.map((u) => [
    u.email.trim().toLowerCase(),
    {
      password: u.password,
      user: {
        id: `user-${u.email}`,
        email: u.email,
        nombre: u.nombre,
        rol: u.rol,
        initials: u.initials,
      } satisfies AdminUser,
    },
  ])
);

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      usuario: null,
      isAuthenticated: false,
      isLoading: false,
      loginError: null,
      returnTo: null,

      setReturnTo: (path) => set({ returnTo: path }),

      loginWithCredentials: async (email, password) => {
        set({ isLoading: true, loginError: null });
        const entry = USER_MAP[email.trim().toLowerCase()];
        await new Promise((r) => setTimeout(r, 150));
        if (!entry || entry.password !== password) {
          set({ isLoading: false, loginError: 'Credenciales inválidas' });
          return;
        }
        set({
          usuario: entry.user,
          isAuthenticated: true,
          isLoading: false,
          loginError: null,
        });
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
    { name: 'duckclaw-admin-auth' }
  )
);

export function authHeadersForBff(rol: AdminRole | undefined): HeadersInit {
  return { 'x-duckclaw-role': rol ?? 'viewer' };
}
