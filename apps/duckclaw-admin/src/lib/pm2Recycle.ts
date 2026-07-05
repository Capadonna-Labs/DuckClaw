/** Recrea procesos PM2 sin `--update-env` (evita contaminación desde `next dev`). */

import { PM2_NODE_DEV_ENV_FILTER } from '@/lib/pm2NodeDevEnvFilter';

function pm2RecycleShell(
  kind: keyof typeof PM2_NODE_DEV_ENV_FILTER.pm2_processes,
  repoRoot: string,
  successToken: string
): string {
  const entry = PM2_NODE_DEV_ENV_FILTER.pm2_processes[kind];
  const startCmd = entry.only_flag
    ? `pm2 start ${entry.ecosystem} ${entry.only_flag}`
    : `pm2 start ${entry.ecosystem}`;
  return `cd "${repoRoot}"
pm2 delete ${entry.name} 2>/dev/null || true
${startCmd}
echo "${successToken}"
`;
}

export function pm2RecycleGatewayShell(repoRoot: string): string {
  return pm2RecycleShell('gateway', repoRoot, 'PM2_RECYCLE_GATEWAY_OK');
}

export function pm2RecycleDbWriterShell(repoRoot: string): string {
  return pm2RecycleShell('db_writer', repoRoot, 'PM2_RECYCLE_DB_WRITER_OK');
}
