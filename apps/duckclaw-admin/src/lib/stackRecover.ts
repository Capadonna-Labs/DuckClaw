import { join } from 'path';
import { spawn } from 'child_process';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { opsSubprocessEnv } from '@/lib/opsSubprocessEnv';
import { buildUvRunArgv } from '@/lib/resolveRepoRuntime';
import { runStackRestartCoreLocal } from '@/lib/stackRestartCore';

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

const PREPARE_MIGRATE_PY = [
  'from pathlib import Path',
  'from duckops.stack_shutdown import prepare_duckdb_for_migrate',
  'raise SystemExit(prepare_duckdb_for_migrate(Path(".").resolve()))',
].join('; ');

/**
 * Detiene PM2 (Gateway/Writer/Indexer/Heartbeat), libera locks DuckDB,
 * aplica migraciones/seeders y vuelve a levantar el stack.
 */
export async function runStackRecoverLocal(): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
  const chunks: string[] = [];

  const prepareArgv = buildUvRunArgv(['python', '-c', PREPARE_MIGRATE_PY]);
  const prepare = await runArgv(cwd, prepareArgv, 90_000);
  chunks.push(
    '── Detener stack + liberar locks DuckDB (antes de migrate) ──\n',
    prepare.stdout,
    prepare.stderr
  );
  if (prepare.exit_code !== 0) {
    return normalizeOpsResult({
      op_id: 'restart_stack',
      exit_code: prepare.exit_code,
      stdout: chunks.join('\n'),
      stderr:
        'No se pudo liberar el lock de DuckDB. Revisa PIDs arriba o ejecuta: uv run duckops down --all --no-admin',
      executed_via: 'local',
      ok: false,
    });
  }

  const migrateArgv = buildUvRunArgv(['duckclaw-migrate']);
  const migrate = await runArgv(cwd, migrateArgv, 180_000);
  chunks.push('\n── Migraciones DuckDB (incl. seeders de policy pack) ──\n', migrate.stdout, migrate.stderr);
  const migrateFailed = migrate.exit_code !== 0;
  if (migrateFailed) {
    chunks.push(
      '\n⚠ duckclaw-migrate falló; se intentará levantar Gateway/DB-Writer igualmente.\n',
      migrate.stderr.trim() ? `Detalle: ${migrate.stderr.trim()}\n` : ''
    );
  } else if (migrate.stderr.trim()) {
    chunks.push(
      '\n(nota: avisos de drift en migraciones son informativos si aparece «Migrated OK»)\n'
    );
  }

  const start = await runStackRestartCoreLocal();
  chunks.push('\n── Arranque PM2 (Gateway + DB-Writer + Heartbeat) ──\n', start.stdout, start.stderr);

  const startOk = start.exit_code === 0;
  return normalizeOpsResult({
    op_id: 'restart_stack',
    exit_code: startOk ? (migrateFailed ? migrate.exit_code : 0) : start.exit_code,
    stdout: chunks.join('\n'),
    stderr: startOk && migrateFailed
      ? 'Migraciones con error, pero PM2 relanzado. Revisa logs de duckclaw-migrate.'
      : start.stderr,
    executed_via: 'local',
    ok: startOk,
  });
}
