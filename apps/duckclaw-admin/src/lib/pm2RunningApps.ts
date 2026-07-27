import { gatewayHealthOk } from '@/lib/gatewayHealthCheck';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';
import { GATEWAY_PM2_CANDIDATES } from '@/lib/pm2AppResolve';
import { gatewayManagedBySystemd } from '@/lib/gatewaySystemd';
import { parsePm2Jlist, pm2JlistStdoutSync } from '@/lib/pm2Jlist';

/** PM2 process names that satisfy each loggable app slot. */
const PM2_NAME_ALIASES: Record<(typeof PM2_LOGGABLE_APPS)[number], readonly string[]> = {
  'DuckClaw-Gateway': GATEWAY_PM2_CANDIDATES,
  'DuckClaw-DB-Writer': ['DuckClaw-DB-Writer', 'duckclaw-db-writer'],
  'DuckClaw-MCP': ['DuckClaw-MCP', 'duckclaw-mcp'],
  'MLX-Vision': ['MLX-Vision', 'mlx-vision'],
  ComfyUI: ['ComfyUI', 'comfyui'],
};

type Pm2Row = { name?: string; pm2_env?: { status?: string } };

function pm2OnlineNames(): Set<string> {
  const rows = parsePm2Jlist(pm2JlistStdoutSync()) as Pm2Row[];
  return new Set(
    rows
      .filter((proc) => proc.pm2_env?.status === 'online')
      .map((proc) => (proc.name || '').trim())
      .filter(Boolean)
  );
}

function isLoggableAppOnline(canonical: (typeof PM2_LOGGABLE_APPS)[number], online: Set<string>): boolean {
  const aliases = PM2_NAME_ALIASES[canonical] ?? [canonical];
  return aliases.some((name) => online.has(name));
}

/** Procesos PM2 (u HTTP health / systemd para gateway) considerados en línea en este host. */
export function listRunningPm2AppNames(): string[] {
  const online = pm2OnlineNames();
  const running = PM2_LOGGABLE_APPS.filter((name) => {
    if (name === 'DuckClaw-Gateway' && gatewayManagedBySystemd()) return false;
    return isLoggableAppOnline(name, online);
  });
  return running;
}

/** Async variant: incluye gateway vía /health si systemd lo gestiona o no hay PM2 online. */
export async function listRunningPm2AppNamesAsync(): Promise<string[]> {
  const running = listRunningPm2AppNames();
  if (!running.includes('DuckClaw-Gateway') && (await gatewayHealthOk())) {
    return ['DuckClaw-Gateway', ...running.filter((name) => name !== 'DuckClaw-Gateway')];
  }
  return running;
}
