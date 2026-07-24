import { spawn } from 'child_process';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { repoRoot } from '@/lib/localOps';

/** Tailscale up + funnel + register_webhooks + check (host local). */
export async function runTelegramIngressStartLocal(): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
  return new Promise((resolve, reject) => {
    const proc = spawn('uv', ['run', 'duckops', 'ingress', 'telegram-start'], { cwd, env: process.env });
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
      reject(new Error('Timeout activando Tailscale (120s)'));
    }, 120_000);
    proc.on('close', (code) => {
      clearTimeout(timer);
      resolve(
        normalizeOpsResult({
          op_id: 'start_telegram_ingress',
          exit_code: code ?? 1,
          stdout: stdout.slice(-12_000),
          stderr: stderr.slice(-8_000),
          executed_via: 'local',
        })
      );
    });
    proc.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}
