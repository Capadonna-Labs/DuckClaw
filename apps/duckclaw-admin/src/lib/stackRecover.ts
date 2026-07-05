import { spawn } from 'child_process';
import { join } from 'path';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { opsSubprocessEnv } from '@/lib/opsSubprocessEnv';
import { pm2WaitShellPreamble } from '@/lib/pm2WaitShell';
import { runStackStartLocal } from '@/lib/stackStart';

function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

function runArgv(
  cwd: string,
  argv: string[],
  timeoutMs = 120_000
): Promise<{ exit_code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(argv[0], argv.slice(1), {
      cwd,
      env: opsSubprocessEnv(),
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

  const stopShell = `${pm2WaitShellPreamble()}
cd "${cwd}"
pm2 stop DuckClaw-Gateway 2>/dev/null || true
pm2 stop DuckClaw-DB-Writer 2>/dev/null || true
wait_pm2_stopped DuckClaw-Gateway 15 || true
wait_pm2_stopped DuckClaw-DB-Writer 15 || true
echo "PM2_STOP_OK"
`;
  const stop = await runArgv(cwd, ['bash', '-lc', stopShell], 60_000);
  chunks.push('── Detener Gateway + DB-Writer (liberar DuckDB) ──\n', stop.stdout, stop.stderr);

  const migrate = await runArgv(cwd, ['uv', 'run', 'duckclaw-migrate'], 180_000);
  chunks.push('\n── Migraciones DuckDB (incl. seeders de policy pack) ──\n', migrate.stdout, migrate.stderr);
  if (migrate.exit_code !== 0) {
    return normalizeOpsResult({
      op_id: 'restart_stack',
      exit_code: migrate.exit_code,
      stdout: chunks.join('\n'),
      stderr: 'duckclaw-migrate falló; revisa locks DuckDB o ejecuta: uv run duckclaw-migrate',
      executed_via: 'local',
    });
  }
  if (migrate.stderr.trim()) {
    chunks.push(
      '\n(nota: avisos de drift en migraciones son informativos si aparece «Migrated OK»)\n'
    );
  }

  const start = await runStackStartLocal();
  chunks.push('\n── Arranque PM2 + ingress ──\n', start.stdout, start.stderr);

  return normalizeOpsResult({
    op_id: 'restart_stack',
    exit_code: start.exit_code,
    stdout: chunks.join('\n'),
    stderr: start.stderr,
    executed_via: 'local',
  });
}
