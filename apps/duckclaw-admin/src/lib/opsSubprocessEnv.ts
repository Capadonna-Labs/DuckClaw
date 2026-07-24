/**
 * Entorno mínimo para subprocess del BFF (PM2, uv, bash).
 * Evita inyectar variables de `next dev` (npm_*, NEXT_*, NODE_OPTIONS=8GB) en DuckClaw-Gateway.
 * Lista canónica: packages/shared/src/duckclaw/seeds/pm2_node_dev_env_filter_v1.json
 */

import {
  isPm2NodeDevAllowedKey,
  isPm2NodeDevBlockedKey,
  PM2_NODE_DEV_ENV_FILTER,
} from '@/lib/pm2NodeDevEnvFilter';

const ALLOWED_KEYS = new Set(PM2_NODE_DEV_ENV_FILTER.allowed_keys);

function augmentPathForOps(pathValue: string | undefined): string {
  const home = process.env.HOME?.trim() || '/root';
  // Homebrew primero: en Mac Mini `pm2` vive en /opt/homebrew/bin; sin eso
  // «Reiniciar sistema» hace `pm2 stop … || true` en silencio y migrate choca
  // con el lock del Gateway.
  const prefixes = [
    '/opt/homebrew/bin',
    '/usr/local/bin',
    `${home}/.local/bin`,
  ].filter((p, i, arr) => arr.indexOf(p) === i);
  const base = (pathValue || '').trim();
  if (!base) return prefixes.join(':');
  const missing = prefixes.filter((p) => !base.split(':').includes(p));
  return missing.length ? [...missing, base].join(':') : base;
}

export function opsSubprocessEnv(extra?: Record<string, string>): NodeJS.ProcessEnv {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value == null || value === '') continue;
    if (isPm2NodeDevAllowedKey(key)) {
      out[key] = value;
      continue;
    }
    if (isPm2NodeDevBlockedKey(key)) continue;
    if (ALLOWED_KEYS.has(key)) out[key] = value;
  }
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value == null || value === '') continue;
      if (isPm2NodeDevBlockedKey(key) && !key.startsWith('DUCKCLAW_')) continue;
      out[key] = value;
    }
  }
  out.PATH = augmentPathForOps(out.PATH);
  return out as NodeJS.ProcessEnv;
}
