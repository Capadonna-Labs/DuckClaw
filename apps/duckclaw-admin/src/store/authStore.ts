import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AdminRole, AdminUser } from '@/types/admin';

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

const HARDCODED: Record<string, { password: string; user: AdminUser }> = {
  'admin@duckclaw.local': {
    password: 'DuckAdmin2026!',
    user: {
      id: 'admin-001',
      email: 'admin@duckclaw.local',
      nombre: 'Administrador DuckClaw',
      rol: 'admin',
      initials: 'DC',
    },
  },
  'viewer@duckclaw.local': {
    password: 'DuckView2026!',
    user: {
      id: 'viewer-001',
      email: 'viewer@duckclaw.local',
      nombre: 'Observador DuckClaw',
      rol: 'viewer',
      initials: 'DV',
    },
  },
};

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
        const entry = HARDCODED[email.trim().toLowerCase()];
        await new Promise((r) => setTimeout(r, 200));
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

      logout: () =>
        set({
          usuario: null,
          isAuthenticated: false,
          loginError: null,
          returnTo: null,
        }),
    }),
    { name: 'duckclaw-admin-auth' }
  )
);

export function authHeadersForBff(rol: AdminRole | undefined): HeadersInit {
  return { 'x-duckclaw-role': rol ?? 'viewer' };
}
