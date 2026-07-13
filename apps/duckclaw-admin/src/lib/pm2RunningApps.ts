import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';
import { parsePm2Jlist, pm2JlistStdoutSync } from '@/lib/pm2Jlist';

/** Procesos PM2 realmente registrados en este host (pm2 jlist). */
export function listRunningPm2AppNames(): string[] {
  const rows = parsePm2Jlist(pm2JlistStdoutSync()) as Array<{ name?: string }>;
  const names = new Set(rows.map((proc) => (proc.name || '').trim()).filter(Boolean));
  return PM2_LOGGABLE_APPS.filter((name) => names.has(name));
}
