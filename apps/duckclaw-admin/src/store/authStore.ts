import { create } from 'zustand';
import type { AdminRole, AdminUser } from '@/types/admin';
import { normalizeAdminRole } from '@/lib/roles';
import { writeAuthSnapshot } from '@/lib/authSessionCache';

function parseLoginError(status: number, data: unknown): string {
  if (status === 429) return 'Demasiados intentos. Espera un momento.';
  if (status >= 500) return 'Error interno del servidor. Reintenta en unos segundos.';
  if (data && typeof data === 'object') {
    const root = data as Record<string, unknown>;
    if (root.code === 'gateway_unreachable') {
      return 'Gateway no disponible. La consola reintentará cuando termine de iniciar.';
    }
    if (typeof root.detail === 'string' && root.detail.toLowerCase().includes('invalid')) {
      return 'Correo o contraseña inválidos';
    }
  }
  if (status === 503) return 'Gateway no disponible. Revisa el estado de la plataforma.';
  return 'Correo o contraseña inválidos';
}

interface AuthState {
  usuario: AdminUser | null;
  isAuthenticated: boolean;
  isSubmitting: boolean;
  loginError: string | null;
  authError: string | null;
  returnTo: string | null;
  hasHydrated: boolean;

  setUser: (user: AdminUser | null) => void;
  loginWithCredentials: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setReturnTo: (path: string | null) => void;
  setHasHydrated: (value: boolean) => void;
  setAuthError: (message: string | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  usuario: null,
  isAuthenticated: false,
  isSubmitting: false,
  loginError: null,
  authError: null,
  returnTo: null,
  hasHydrated: false,

  setUser: (user) => {
    writeAuthSnapshot(user);
    set({
      usuario: user,
      isAuthenticated: Boolean(user),
    });
  },

  setReturnTo: (path) => set({ returnTo: path }),

  setHasHydrated: (value) => set({ hasHydrated: value }),

  setAuthError: (message) => set({ authError: message }),

  loginWithCredentials: async (email, password) => {
    set({ isSubmitting: true, loginError: null });
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
        set({ isSubmitting: false, loginError: parseLoginError(res.status, data) });
        return;
      }
      const raw = (data.user ?? data) as Record<string, unknown>;
      const profileRaw = raw.profile;
      const tenantId =
        profileRaw &&
        typeof profileRaw === 'object' &&
        typeof (profileRaw as Record<string, unknown>).tenant_id === 'string'
          ? String((profileRaw as Record<string, unknown>).tenant_id).trim()
          : '';
      const user: AdminUser = {
        id: String(raw.id ?? `user-${raw.email}`),
        email: String(raw.email),
        nombre: String(raw.nombre ?? raw.email),
        rol: normalizeAdminRole(raw.rol) as AdminRole,
        initials: String(raw.initials ?? String(raw.email).slice(0, 2).toUpperCase()),
        profile: tenantId ? { tenant_id: tenantId } : undefined,
      };
      writeAuthSnapshot(user);
      set({
        usuario: user,
        isAuthenticated: true,
        isSubmitting: false,
        loginError: null,
        authError: null,
      });
    } catch {
      set({ isSubmitting: false, loginError: 'No se pudo conectar con el servidor' });
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
    writeAuthSnapshot(null);
    set({
      usuario: null,
      isAuthenticated: false,
      isSubmitting: false,
      loginError: null,
      authError: null,
      returnTo: get().returnTo,
    });
  },
}));

export function adminPostAuthPath(returnTo: string | null | undefined): string {
  if (returnTo && returnTo.startsWith('/') && returnTo !== '/login') {
    return returnTo;
  }
  return '/playground';
}

/** @deprecated RBAC is server-derived; kept for compatibility during migration. */
export function authHeadersForBff(): HeadersInit {
  return {};
}
