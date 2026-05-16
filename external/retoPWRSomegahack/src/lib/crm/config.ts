/**
 * Configuración CRM ↔ DuckDB bóveda (spec: specs/features/CRM PQRSD persistencia DuckDB.md).
 * Prioridad de ruta alineada con el monorepo DuckClaw (`DUCKCLAW_PQRSD_ASSISTANT_DB_PATH`).
 */
import path from 'path';

/** Raíz del repo Duckclaw (donde vive `db/private/...`). */
export function duckclawRepoRoot(): string {
  const env = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (env) {
    return path.resolve(env);
  }
  // Por defecto: `external/retoPWRSomegahack` → dos niveles arriba = raíz del monorepo
  return path.resolve(process.cwd(), '../..');
}

/**
 * Ruta absoluta al .duckdb compartido con PQRSD-Assistant.
 * Orden: DUCKCLAW_PQRSD_ASSISTANT_DB_PATH → CRM_DUCKDB_PATH → fallback dev.
 */
export function resolvePqrsAssistantDuckDbPath(): string {
  const pqrs = process.env.DUCKCLAW_PQRSD_ASSISTANT_DB_PATH?.trim();
  const crm = process.env.CRM_DUCKDB_PATH?.trim();
  const raw = pqrs || crm;
  const root = duckclawRepoRoot();
  if (!raw) {
    return path.resolve(root, 'db/private/1726618406/pqrsd-assistantdb1.duckdb');
  }
  if (path.isAbsolute(raw)) {
    return raw;
  }
  return path.resolve(root, raw);
}

/** Misma bóveda que el worker PQRSD-Assistant; usada por Gateway (db/read, db/write). */
export function crmDuckDbPath(): string {
  return resolvePqrsAssistantDuckDbPath();
}

/** user_id de bóveda para Gateway (db/read y db/write). */
export function crmVaultUserId(): string {
  return (
    process.env.CRM_VAULT_USER_ID?.trim() ||
    process.env.DUCKCLAW_GATEWAY_USER_ID_OVERRIDE?.trim() ||
    '1726618406'
  );
}

export function crmTenantId(): string {
  return process.env.CRM_TENANT_ID?.trim() || 'PQRS';
}

export function crmAutoBootstrap(): boolean {
  return process.env.CRM_AUTO_BOOTSTRAP === 'true';
}
