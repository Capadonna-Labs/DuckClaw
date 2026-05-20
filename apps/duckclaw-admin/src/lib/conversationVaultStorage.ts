/** Persistencia local de bóveda DuckDB por conversación (admin UI). */

export function vaultStorageKey(chatId: string): string {
  return `duckclaw-admin-vault-${chatId}`;
}

export function readStoredVaultPath(chatId: string): string | null {
  if (typeof window === 'undefined' || !chatId) return null;
  try {
    return sessionStorage.getItem(vaultStorageKey(chatId));
  } catch {
    return null;
  }
}

export function writeStoredVaultPath(chatId: string, path: string): void {
  if (typeof window === 'undefined' || !chatId) return;
  try {
    if (path) {
      sessionStorage.setItem(vaultStorageKey(chatId), path);
    } else {
      sessionStorage.removeItem(vaultStorageKey(chatId));
    }
  } catch {
    /* ignore quota */
  }
}
