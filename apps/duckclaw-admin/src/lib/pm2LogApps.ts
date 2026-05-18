/** Procesos PM2 permitidos para logs en vivo (admin local). */

export const PM2_LOGGABLE_APPS = [
  'DuckClaw-Gateway',
  'DuckClaw-DB-Writer',
  'DuckClaw-MCP',
  'MLX-Vision',
] as const;

export type Pm2LogApp = (typeof PM2_LOGGABLE_APPS)[number];

const ALLOWED = new Set<string>(PM2_LOGGABLE_APPS);

export function parsePm2LogAppsParam(raw: string | null): {
  ok: true;
  names: string[];
} | {
  ok: false;
  error: string;
} {
  const parts = (raw ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  if (parts.length === 0) {
    return { ok: false, error: 'Indica al menos un servicio (máx. 2)' };
  }
  if (parts.length > 2) {
    return { ok: false, error: 'Máximo 2 servicios a la vez' };
  }

  const names: string[] = [];
  for (const p of parts) {
    if (!ALLOWED.has(p)) {
      return { ok: false, error: `Servicio no permitido: ${p}` };
    }
    if (names.includes(p)) continue;
    names.push(p);
  }

  return { ok: true, names };
}
