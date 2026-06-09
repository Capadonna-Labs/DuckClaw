import { execSync } from 'child_process';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';

/** Procesos PM2 realmente registrados en este host (pm2 jlist). */
export function listRunningPm2AppNames(): string[] {
  try {
    const raw = execSync('pm2 jlist', { encoding: 'utf8', timeout: 8000 });
    const parsed = JSON.parse(raw) as Array<{ name?: string }>;
    const names = new Set(
      parsed.map((proc) => (proc.name || '').trim()).filter(Boolean)
    );
    return PM2_LOGGABLE_APPS.filter((name) => names.has(name));
  } catch {
    return [...PM2_LOGGABLE_APPS];
  }
}
