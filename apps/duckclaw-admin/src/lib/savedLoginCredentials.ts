/** Saved login for desktop/local admin — only after explicit user consent. */

const STORAGE_KEY = 'duckclaw.admin.saved_login.v1';

export type SavedLoginCredentials = {
  email: string;
  password: string;
};

export function readSavedLoginCredentials(): SavedLoginCredentials | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as SavedLoginCredentials;
    const email = (data.email || '').trim();
    const password = data.password || '';
    if (!email || !password) return null;
    return { email, password };
  } catch {
    return null;
  }
}

export function saveSavedLoginCredentials(creds: SavedLoginCredentials): void {
  if (typeof window === 'undefined') return;
  const email = creds.email.trim();
  const password = creds.password;
  if (!email || !password) return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ email, password }));
}

export function clearSavedLoginCredentials(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function confirmSaveLoginCredentials(): boolean {
  return window.confirm(
    '¿Guardar la contraseña en este equipo?\n\nSe guardará en el almacenamiento local de DuckClaw Admin. Solo acepta si confías en este dispositivo y usuario de Windows.'
  );
}
