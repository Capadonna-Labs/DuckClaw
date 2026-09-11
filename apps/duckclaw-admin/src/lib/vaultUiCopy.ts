/** Minimal ES/EN copy for vault create + assign UI (no full i18n stack). */

export type VaultUiLocale = 'es' | 'en';

const COPY = {
  es: {
    vault: 'Bóveda',
    newVault: 'Nueva bóveda',
    name: 'Nombre',
    descriptionOptional: 'Descripción (opcional)',
    create: 'Crear',
    creating: 'Creando…',
    cancel: 'Cancelar',
    nameRequired: 'Indica un nombre para la bóveda',
    createFailed: 'No se pudo crear la bóveda',
    createdPrefix: 'Bóveda creada:',
    noVaults: '(sin bóvedas)',
    activeSuffix: ' activa',
    panelTitle: 'Bóveda DuckDB (/vault)',
    panelHelp:
      'Archivos en db/private/<tu id>/ y db/shared/. Afecta /vault y el sandbox de esta plantilla.',
    vaultUserId: 'ID bóveda (usuario)',
    duckdbFile: 'Archivo .duckdb',
    noBinding: '— Sin binding (hub / registry) —',
    privateGroup: 'Privadas (tu usuario)',
    sharedGroup: 'Compartidas',
    resolvedPath: 'Ruta resuelta:',
    refreshList: 'Actualizar lista',
    saveVault: 'Guardar bóveda',
    savingVault: 'Guardando bóveda…',
    savedManifest: 'Bóveda guardada en manifest.yaml',
    unbound: 'Bóveda desvinculada (hub / registry por defecto)',
    saveFailed: 'Error al guardar',
    saveVaultAction: 'Guardar bóveda',
  },
  en: {
    vault: 'Vault',
    newVault: 'New vault',
    name: 'Name',
    descriptionOptional: 'Description (optional)',
    create: 'Create',
    creating: 'Creating…',
    cancel: 'Cancel',
    nameRequired: 'Enter a vault name',
    createFailed: 'Could not create vault',
    createdPrefix: 'Vault created:',
    noVaults: '(no vaults)',
    activeSuffix: ' active',
    panelTitle: 'DuckDB vault (/vault)',
    panelHelp:
      'Files under db/private/<your id>/ and db/shared/. Affects /vault and this template sandbox.',
    vaultUserId: 'Vault user id',
    duckdbFile: '.duckdb file',
    noBinding: '— No binding (hub / registry) —',
    privateGroup: 'Private (your user)',
    sharedGroup: 'Shared',
    resolvedPath: 'Resolved path:',
    refreshList: 'Refresh list',
    saveVault: 'Save vault',
    savingVault: 'Saving vault…',
    savedManifest: 'Vault saved to manifest.yaml',
    unbound: 'Vault unbound (default hub / registry)',
    saveFailed: 'Failed to save',
    saveVaultAction: 'Save vault',
  },
} as const;

export type VaultUiCopy = (typeof COPY)['es'];

export function resolveVaultUiLocale(raw?: string | null): VaultUiLocale {
  const value = (raw || '').toLowerCase();
  return value.startsWith('en') ? 'en' : 'es';
}

export function vaultUiCopy(locale?: string | null): VaultUiCopy {
  return COPY[resolveVaultUiLocale(locale)];
}

export function browserVaultUiCopy(): VaultUiCopy {
  if (typeof navigator === 'undefined') return COPY.es;
  return vaultUiCopy(navigator.language);
}
