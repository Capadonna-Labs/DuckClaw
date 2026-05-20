import { appendFileSync } from 'fs';
import { spawn } from 'child_process';
import { join } from 'path';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { runTelegramIngressStartLocal } from '@/lib/telegramIngressStart';

// #region agent log
function agentLog(
  hypothesisId: string,
  location: string,
  message: string,
  data: Record<string, unknown>
) {
  try {
    const logPath = join(repoRoot(), '.cursor', 'debug-fd1dbb.log');
    appendFileSync(
      logPath,
      `${JSON.stringify({
        sessionId: 'fd1dbb',
        hypothesisId,
        location,
        message,
        data,
        timestamp: Date.now(),
      })}\n`
    );
  } catch {
    /* ignore */
  }
}
// #endregion

const SYNC_PM2 = [
  'uv',
  'run',
  'python',
  '-c',
  [
    'from pathlib import Path',
    'from duckops.sovereign.pm2_dotenv_sync import rerender_gateway_pm2_ecosystem',
    'rerender_gateway_pm2_ecosystem(Path(".").resolve())',
    'print("PM2 config sincronizado")',
  ].join('; '),
];

function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

function runArgv(
  cwd: string,
  argv: string[],
  timeoutMs = 120_000,
  extraEnv?: Record<string, string>
): Promise<{ exit_code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(argv[0], argv.slice(1), {
      cwd,
      env: { ...process.env, ...extraEnv },
    });
    let stdout = '';
    let stderr = '';
    proc.stdout?.on('data', (d) => {
      stdout += String(d);
    });
    proc.stderr?.on('data', (d) => {
      stderr += String(d);
    });
    const timer = setTimeout(() => {
      proc.kill('SIGTERM');
      reject(new Error('Timeout arrancando stack (120s)'));
    }, timeoutMs);
    proc.on('close', (code) => {
      clearTimeout(timer);
      resolve({
        exit_code: code ?? 1,
        stdout: stdout.slice(-12_000),
        stderr: stderr.slice(-8_000),
      });
    });
    proc.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/** Arranca o reinicia DB-Writer y Gateway bajo PM2 (host local del admin). */
export async function runStackStartLocal(): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
  const chunks: string[] = [];
  // #region agent log
  agentLog('A', 'stackStart.ts:runStackStartLocal', 'start_stack begin', { cwd });
  // #endregion

  const sync = await runArgv(cwd, SYNC_PM2);
  chunks.push('── Sincronizar PM2 desde .env ──\n', sync.stdout, sync.stderr);
  if (sync.exit_code !== 0) {
    return normalizeOpsResult({
      op_id: 'start_stack',
      exit_code: sync.exit_code,
      stdout: chunks.join('\n'),
      stderr: '',
      executed_via: 'local',
    });
  }

  const lockCheck = await runArgv(
    cwd,
    ['uv', 'run', 'python', 'scripts/check_duckdb_lock_holders.py'],
    30_000
  );
  let blocking: Array<{ pid: number; db: string; kind: string; command: string }> = [];
  try {
    const parsed = JSON.parse(lockCheck.stdout.trim() || '{}') as {
      blocking?: Array<{ pid: number; db: string; kind: string; command: string }>;
    };
    blocking = parsed.blocking ?? [];
  } catch {
    /* ignore parse */
  }
  // #region agent log
  agentLog('A', 'stackStart.ts:lock_check', 'duckdb lock preflight', {
    blocking_count: blocking.length,
    blocking: blocking.slice(0, 5),
    exit_code: lockCheck.exit_code,
  });
  // #endregion
  if (blocking.length > 0) {
    const lines = blocking.map(
      (b) => `  PID ${b.pid} (${b.kind}): ${b.db}\n    ${b.command}`
    );
    chunks.push(
      '\n── Bloqueo DuckDB (detén estos procesos antes de arrancar) ──\n',
      ...lines,
      '\nEjemplo: kill ',
      String(blocking[0]?.pid ?? ''),
      '\n'
    );
    return normalizeOpsResult({
      op_id: 'start_stack',
      exit_code: 3,
      stdout: chunks.join('\n'),
      stderr:
        'Hay procesos externos (p. ej. pytest) con lock exclusivo en db/private. Deténlos y vuelve a intentar.',
      executed_via: 'local',
    });
  }

  const shell = `cd "${cwd}"
GATEWAY_MODE="start"
pm2 stop DuckClaw-Gateway 2>/dev/null || true
pm2 stop DuckClaw-DB-Writer 2>/dev/null || true
sleep 2
if pm2 describe DuckClaw-DB-Writer >/dev/null 2>&1; then
  pm2 start DuckClaw-DB-Writer --update-env || pm2 restart DuckClaw-DB-Writer --update-env
else
  pm2 start config/ecosystem.db-writer.config.cjs --update-env
fi
sleep 2
if pm2 describe DuckClaw-Gateway >/dev/null 2>&1; then
  GATEWAY_MODE="restart"
  pm2 start DuckClaw-Gateway --update-env || pm2 restart DuckClaw-Gateway --update-env
else
  pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway --update-env
fi
echo "GATEWAY_PM2_MODE=$GATEWAY_MODE"
pm2 save 2>/dev/null || true
sleep 3
pm2 list
`;
  const proc = await runArgv(cwd, ['bash', '-lc', shell], 180_000);
  chunks.push('\n── DuckClaw-DB-Writer + DuckClaw-Gateway ──\n', proc.stdout, proc.stderr);
  const gatewayMode = /GATEWAY_PM2_MODE=(\w+)/.exec(proc.stdout)?.[1] ?? 'unknown';
  // #region agent log
  agentLog('A', 'stackStart.ts:pm2', 'pm2 gateway step done', {
    gatewayMode,
    exit_code: proc.exit_code,
  });
  // #endregion

  if (proc.exit_code !== 0) {
    return normalizeOpsResult({
      op_id: 'start_stack',
      exit_code: proc.exit_code,
      stdout: chunks.join('\n'),
      stderr: '',
      executed_via: 'local',
    });
  }

  const telegram = await runTelegramIngressStartLocal();
  chunks.push('\n── Tailscale + Telegram (webhook) ──\n', telegram.stdout, telegram.stderr);
  // #region agent log
  agentLog('B', 'stackStart.ts:telegram', 'telegram ingress done', {
    exit_code: telegram.exit_code,
  });
  // #endregion

  const serve = await runArgv(
    cwd,
    ['uv', 'run', 'python', 'scripts/restore_tailscale_admin_serve.py'],
    60_000
  );
  const adminPort =
    /ADMIN_SERVE_PORT=(\d+)/.exec(serve.stdout)?.[1] ??
    process.env.DUCKCLAW_ADMIN_PORT?.trim() ??
    'unknown';
  chunks.push(
    '\n── Tailscale Serve admin (:8443) ──\n',
    serve.stdout,
    serve.stderr
  );
  // #region agent log
  agentLog('C', 'stackStart.ts:serve', 'admin tailscale serve', {
    adminPort,
    exit_code: serve.exit_code,
  });
  agentLog('B', 'stackStart.ts:funnel', 'post-telegram serve restore', {
    serveExit: serve.exit_code,
  });
  // #endregion

  if (serve.exit_code !== 0) {
    chunks.push(
      '\nwarn: no se pudo re-aplicar Tailscale Serve :8443; ejecuta scripts/tailscale_serve_admin.sh\n'
    );
  }

  return normalizeOpsResult({
    op_id: 'start_stack',
    exit_code: telegram.exit_code,
    stdout: chunks.join('\n'),
    stderr: telegram.stderr,
    executed_via: 'local',
  });
}
