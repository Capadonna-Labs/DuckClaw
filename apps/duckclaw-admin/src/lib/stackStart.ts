import { spawn } from 'child_process';
import { join } from 'path';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { runTelegramIngressStartLocal } from '@/lib/telegramIngressStart';

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
  timeoutMs = 120_000
): Promise<{ exit_code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(argv[0], argv.slice(1), { cwd, env: process.env });
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

  const shell = `set -e
cd "${cwd}"
if pm2 describe DuckClaw-DB-Writer >/dev/null 2>&1; then
  pm2 restart DuckClaw-DB-Writer --update-env || pm2 start config/ecosystem.db-writer.config.cjs --update-env
else
  pm2 start config/ecosystem.db-writer.config.cjs --update-env
fi
if pm2 describe DuckClaw-Gateway >/dev/null 2>&1; then
  pm2 delete DuckClaw-Gateway 2>/dev/null || true
fi
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway --update-env
pm2 save 2>/dev/null || true
sleep 2
pm2 list
`;
  const proc = await runArgv(cwd, ['bash', '-lc', shell], 180_000);
  chunks.push('\n── DuckClaw-DB-Writer + DuckClaw-Gateway ──\n', proc.stdout, proc.stderr);

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

  return normalizeOpsResult({
    op_id: 'start_stack',
    exit_code: telegram.exit_code,
    stdout: chunks.join('\n'),
    stderr: telegram.stderr,
    executed_via: 'local',
  });
}
