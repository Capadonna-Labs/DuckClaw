import { create } from 'zustand';
import type { AdminRole, AdminUser } from '@/types/admin';
import { normalizeAdminRole } from '@/lib/roles';

function parseLoginError(status: number, data: unknown): string {
  if (status === 429) return 'Demasiados intentos. Espera un momento.';
  if (data && typeof data === 'object') {
    const root = data as Record<string, unknown>;
    if (typeof root.detail === 'string' && root.detail.toLowerCase().includes('invalid')) {
      return 'Correo o contraseña inválidos';
    }
  }
  return 'Correo o contraseña inválidos';
}

interface AuthState {
  usuario: AdminUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginError: string | null;
  returnTo: string | null;
  hasHydrated: boolean;

  setUser: (user: AdminUser | null) => void;
  setLoading: (value: boolean) => void;
  loginWithCredentials: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setReturnTo: (path: string | null) => void;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  usuario: null,
  isAuthenticated: false,
  isLoading: true,
  loginError: null,
  returnTo: null,
  hasHydrated: false,

  setUser: (user) =>
    set({
      usuario: user,
      isAuthenticated: Boolean(user),
    }),

  setLoading: (value) => set({ isLoading: value }),

  setReturnTo: (path) => set({ returnTo: path }),

  setHasHydrated: (value) => set({ hasHydrated: value }),

  loginWithCredentials: async (email, password) => {
    set({ isLoading: true, loginError: null });
    try {
      const res = await fetch('/api/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim(), password }),
        cache: 'no-store',
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        set({ isLoading: false, loginError: parseLoginError(res.status, data) });
        return;
      }
      const raw = (data.user ?? data) as Record<string, unknown>;
      const user: AdminUser = {
        id: String(raw.id ?? `user-${raw.email}`),
        email: String(raw.email),
        nombre: String(raw.nombre ?? raw.email),
        rol: normalizeAdminRole(raw.rol) as AdminRole,
        initials: String(raw.initials ?? String(raw.email).slice(0, 2).toUpperCase()),
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

  logout: async () => {
    try {
      await fetch('/api/admin/auth/logout', {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
      });
    } catch {
      /* ignore */
    }
    set({
      usuario: null,
      isAuthenticated: false,
      isLoading: false,
      loginError: null,
      returnTo: get().returnTo,
    });
  },
}));

export function adminPostAuthPath(returnTo: string | null | undefined): string {
  if (returnTo && returnTo.startsWith('/') && returnTo !== '/login') {
    return returnTo;
  }
  return '/overview';
}

/** @deprecated RBAC is server-derived; kept for compatibility during migration. */
export function authHeadersForBff(): HeadersInit {
  return {};
}
