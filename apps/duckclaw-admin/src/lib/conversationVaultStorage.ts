/** Persistencia local de bóveda DuckDB por conversación (admin UI). */

const ACTOR_VAULT_KEY = 'duckclaw-admin-vault-actor-default';

export function vaultStorageKey(chatId: string): string {
  return `duckclaw-admin-vault-${chatId}`;
}

export function readStoredVaultPath(chatId: string): string | null {
  if (typeof window === 'undefined' || !chatId) return null;
  try {
    return localStorage.getItem(vaultStorageKey(chatId));
  } catch {
    return null;
  }
}

export function writeStoredVaultPath(chatId: string, path: string): void {
  if (typeof window === 'undefined' || !chatId) return;
  try {
    if (path) {
      localStorage.setItem(vaultStorageKey(chatId), path);
      localStorage.setItem(ACTOR_VAULT_KEY, path);
    } else {
      localStorage.removeItem(vaultStorageKey(chatId));
    }
  } catch {
    /* ignore quota */
  }
}

/** Última bóveda elegida por el actor (nuevas conversaciones / recargas). */
export function readActorDefaultVaultPath(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(ACTOR_VAULT_KEY)?.trim() || null;
  } catch {
    return null;
  }
}
