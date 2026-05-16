import { crmDuckDbPath } from '@/lib/crm/config';
import { gatewayBaseUrl } from '@/lib/duckclaw-gateway';

/** Lectura CRM: DuckDB vía Gateway si hay ruta y URL; si no, mock en memoria. */
export function crmUsesDuckDb(): boolean {
  return Boolean(crmDuckDbPath() && gatewayBaseUrl());
}
