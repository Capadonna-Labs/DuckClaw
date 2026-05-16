import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Usuario } from '@/types';
import { USUARIOS_MOCK } from '@/services/mockData';

/**
 * Modo de datos: determina si el CRM usa datos mock o DuckDB local / Gateway.
 * - 'mock': usuario de prueba con datos estáticos (offline).
 * - 'live': usuario admin conectado a DuckDB vía API Routes.
 */
export type DataMode = 'mock' | 'live';

interface AuthState {
  usuario: Usuario | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  dataMode: DataMode;
  loginError: string | null;

  loginWithCredentials: (email: string, password: string) => Promise<void>;
  login: (idUsuario: string) => Promise<void>;
  logout: () => void;
  setUsuario: (usuario: Usuario) => void;
}

// ── Credenciales hardcodeadas ──
const HARDCODED_USERS: Record<string, { password: string; user: Usuario; mode: DataMode }> = {
  'rraliadosteam@gmail.com': {
    password: 'CRMadmin123',
    mode: 'live',
    user: {
      idUsuario: 'admin-001',
      nombreCompleto: 'Administrador CRM',
      cargo: 'Administrador del Sistema',
      idSecretaria: 'sec-salud',
      secretariaNombre: 'Secretaría de Salud',
      rol: 'admin',
      initials: 'AC',
    },
  },
  'test@rr.com': {
    password: 'test1234',
    mode: 'mock',
    user: USUARIOS_MOCK[0], // María Camila Restrepo
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      usuario: null,
      isAuthenticated: false,
      isLoading: false,
      dataMode: 'mock' as DataMode,
      loginError: null,

      loginWithCredentials: async (email: string, password: string) => {
        set({ isLoading: true, loginError: null });

        await new Promise(resolve => setTimeout(resolve, 600));

        const normalizedEmail = email.trim().toLowerCase();
        const entry = HARDCODED_USERS[normalizedEmail];

        if (!entry) {
          set({ isLoading: false, loginError: 'Correo no registrado en el sistema' });
          throw new Error('Correo no registrado en el sistema');
        }

        if (entry.password !== password) {
          set({ isLoading: false, loginError: 'Contraseña incorrecta' });
          throw new Error('Contraseña incorrecta');
        }

        set({
          usuario: entry.user,
          isAuthenticated: true,
          isLoading: false,
          dataMode: entry.mode,
          loginError: null,
        });
      },

      // Legacy login por ID (mantener para compatibilidad interna)
      login: async (idUsuario: string) => {
        set({ isLoading: true, loginError: null });
        await new Promise(resolve => setTimeout(resolve, 500));

        const user = USUARIOS_MOCK.find(u => u.idUsuario === idUsuario);
        if (user) {
          set({
            usuario: user,
            isAuthenticated: true,
            isLoading: false,
            dataMode: 'mock',
            loginError: null,
          });
        } else {
          set({ isLoading: false, loginError: 'Usuario no encontrado' });
          throw new Error('Usuario no encontrado');
        }
      },

      logout: () => {
        set({
          usuario: null,
          isAuthenticated: false,
          isLoading: false,
          dataMode: 'mock',
          loginError: null,
        });
      },
      setUsuario: (usuario: Usuario) => {
        set({ usuario });
      },
    }),
    {
      name: 'crm-pqrsd-auth',
    }
  )
);

/**
 * Selector hook para obtener el ID de la secretaría activa de forma reactiva.
 */
export const useIdSecretariaActivo = () =>
  useAuthStore((state) => state.usuario?.idSecretaria ?? '');

/**
 * Selector hook para obtener el modo de datos activo.
 */
export const useDataMode = () =>
  useAuthStore((state) => state.dataMode);
