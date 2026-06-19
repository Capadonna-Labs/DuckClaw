/** Etiqueta corta de una ruta .duckdb para chips en UI (sin jerga de bóveda/hub). */

export function shortenSessionDbPath(path: string): string {
  const raw = (path || '').trim();
  if (!raw) return '—';
  const normalized = raw.replace(/\\/g, '/');
  const parts = normalized.split('/').filter(Boolean);
  if (parts.length <= 2) return normalized;
  return `…/${parts.slice(-2).join('/')}`;
}

export function sessionDbScopeLabel(scope?: string): string {
  if (scope === 'chat') return 'Elegida en esta conversación';
  if (scope === 'runtime') return 'Tu preferencia guardada';
  return 'Predeterminada del sistema';
}
