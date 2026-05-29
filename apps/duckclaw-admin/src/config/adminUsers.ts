import type { AdminRole } from '@/types/admin';

/** Usuarios de la consola admin. Edita aquí o sustituye por SSO en producción. */
export type AdminUserConfig = {
  email: string;
  password: string;
  nombre: string;
  rol: AdminRole;
  initials: string;
};

export const ADMIN_USERS: AdminUserConfig[] = [
  {
    email: 'admin@duckclaw.local',
    password: '1234',
    nombre: 'Administrador DuckClaw',
    rol: 'admin',
    initials: 'DC',
  },
  {
    email: 'user@duckclaw.local',
    password: '1234',
    nombre: 'Usuario DuckClaw',
    rol: 'user',
    initials: 'UD',
  }
];

export const DEV_LOGIN_HINT = ADMIN_USERS.map((u) => ({
  email: u.email,
  rol: u.rol,
  passwordHint: u.rol === 'admin' ? '1234' : '1234',
}));
