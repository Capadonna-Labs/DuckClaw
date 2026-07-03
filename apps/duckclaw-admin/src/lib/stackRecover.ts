import { spawn } from 'child_process';
import { join } from 'path';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { runStackStartLocal } from '@/lib/stackStart';

const DEBUG_LOG_ENDPOINT = 'http://127.0.0.1:7477/ingest/4cb00f05-d949-473c-91c2-92e570fd43ec';
const DEBUG_SESSION_ID = 'ab0734';

function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

// #region agent log
function agentLog(
  hypothesisId: string,
  location: string,
  message: string,
  data: Record<string, unknown>
) {
  fetch(DEBUG_LOG_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Debug-Session-Id': DEBUG_SESSION_ID,
    },
    body: JSON.stringify({
      sessionId: DEBUG_SESSION_ID,
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
      runId: 'stack-recover',
    }),
  }).catch(() => {});
}
// #endregion

function runArgv(
  cwd: string,
  argv: string[],
  timeoutMs = 120_000
): Promise<{ exit_code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(argv[0], argv.slice(1), {
      cwd,
      env: process.env,
    });
    let stdout = '';
    let stderr = '';
    proc.stdout?.on('data', (d: Buffer | string) => {
      stdout += String(d);
    });
    proc.stderr?.on('data', (d: Buffer | string) => {
      stderr += String(d);
    });
    const timer = setTimeout(() => {
      proc.kill('SIGTERM');
      reject(new Error(`Timeout (${timeoutMs}ms): ${argv.join(' ')}`));
    }, timeoutMs);
    proc.on('close', (code: number | null) => {
      clearTimeout(timer);
      resolve({
        exit_code: code ?? 1,
        stdout: stdout.slice(-12_000),
        stderr: stderr.slice(-8_000),
      });
    });
    proc.on('error', (err: Error) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/** Detiene PM2, aplica migraciones/seeders vía duckclaw-migrate y levanta el stack. */
export async function runStackRecoverLocal(): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
  const chunks: string[] = [];
  agentLog('H1', 'stackRecover.ts:entry', 'stack recover started', { cwd });

  const stopShell = `cd "${cwd}"
pm2 stop DuckClaw-Gateway 2>/dev/null || true
pm2 stop DuckClaw-DB-Writer 2>/dev/null || true
sleep 2
echo "PM2_STOP_OK"
`;
  const stop = await runArgv(cwd, ['bash', '-lc', stopShell], 60_000);
  chunks.push('── Detener Gateway + DB-Writer (liberar DuckDB) ──\n', stop.stdout, stop.stderr);
  agentLog('H2', 'stackRecover.ts:stop', 'pm2 stop finished', {
    exit_code: stop.exit_code,
    stdout_tail: stop.stdout.slice(-400),
  });

  const migrate = await runArgv(cwd, ['uv', 'run', 'duckclaw-migrate'], 180_000);
  chunks.push('\n── Migraciones DuckDB (incl. seeders de policy pack) ──\n', migrate.stdout, migrate.stderr);
  agentLog('H1', 'stackRecover.ts:migrate', 'duckclaw-migrate finished', {
    exit_code: migrate.exit_code,
    stdout_tail: migrate.stdout.slice(-400),
    stderr_tail: migrate.stderr.slice(-200),
  });
  if (migrate.exit_code !== 0) {
    return normalizeOpsResult({
      op_id: 'restart_stack',
      exit_code: migrate.exit_code,
      stdout: chunks.join('\n'),
      stderr: 'duckclaw-migrate falló; revisa locks DuckDB o ejecuta: uv run duckclaw-migrate',
      executed_via: 'local',
    });
  }

  const start = await runStackStartLocal();
  chunks.push('\n── Arranque PM2 + ingress ──\n', start.stdout, start.stderr);
  agentLog('H3', 'stackRecover.ts:start', 'stack start finished', {
    ok: start.ok,
    exit_code: start.exit_code,
  });

  return normalizeOpsResult({
    op_id: 'restart_stack',
    exit_code: start.exit_code,
    stdout: chunks.join('\n'),
    stderr: start.stderr,
    executed_via: 'local',
  });
}
