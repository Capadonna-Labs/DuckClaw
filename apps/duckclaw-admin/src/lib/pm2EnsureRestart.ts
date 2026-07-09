/** Arranque/reinicio PM2 sin `pm2 delete` — evita dejar el stack vacío si falla el start. */

import { PM2_NODE_DEV_ENV_FILTER } from '@/lib/pm2NodeDevEnvFilter';

function ensureRestartShell(
  kind: keyof typeof PM2_NODE_DEV_ENV_FILTER.pm2_processes,
  repoRoot: string,
  successToken: string
): string {
  const entry = PM2_NODE_DEV_ENV_FILTER.pm2_processes[kind];
  const startCmd = entry.only_flag
    ? `pm2 start ${entry.ecosystem} ${entry.only_flag}`
    : `pm2 start ${entry.ecosystem}`;
  const legacyNames =
    kind === 'gateway'
      ? 'DuckClaw-Gateway duckclaw-gateway DuckClaw-API'
      : entry.name;
  return `cd "${repoRoot}"
_ensured=0
for n in ${legacyNames}; do
  if pm2 describe "$n" >/dev/null 2>&1; then
    pm2 restart "$n" --update-env
    echo "${successToken} $n"
    _ensured=1
    break
  fi
done
if [ "$_ensured" -eq 0 ]; then
  ${startCmd}
  echo "${successToken} started"
fi
`;
}

export function pm2EnsureRestartDbWriterShell(repoRoot: string): string {
  return ensureRestartShell('db_writer', repoRoot, 'PM2_ENSURE_DB_WRITER_OK');
}

export function pm2EnsureRestartGatewayShell(repoRoot: string): string {
  return ensureRestartShell('gateway', repoRoot, 'PM2_ENSURE_GATEWAY_OK');
}

export function pm2EnsureRestartHeartbeatShell(repoRoot: string): string {
  return ensureRestartShell('heartbeat', repoRoot, 'PM2_ENSURE_HEARTBEAT_OK');
}
