import { spawn } from 'child_process';

import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';

import { repoRoot } from '@/lib/localOps';

import { opsSubprocessEnv } from '@/lib/opsSubprocessEnv';

import { pm2EnsureRestartDbWriterShell, pm2EnsureRestartGatewayShell, pm2EnsureRestartHeartbeatShell } from '@/lib/pm2EnsureRestart';

import { pm2WaitShellPreamble } from '@/lib/pm2WaitShell';



function runShell(

  cwd: string,

  shell: string,

  timeoutMs = 180_000

): Promise<{ exit_code: number; stdout: string; stderr: string }> {

  return new Promise((resolve, reject) => {

    const proc = spawn('bash', ['-lc', shell], {

      cwd,

      env: opsSubprocessEnv(),

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

      reject(new Error(`Timeout (${timeoutMs}ms)`));

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



/**

 * Reinicio VPS: DB-Writer + Heartbeat + Gateway (sin Indexer/SYNC_PM2).

 * Usa restart/start — nunca `pm2 delete` salvo heal de entrada corrupta.

 */

export async function runStackRestartCoreLocal(): Promise<NormalizedOpsRunResult> {

  const cwd = repoRoot();

  const shell = `${pm2WaitShellPreamble()}

cd "${cwd}"

heal_pm2_corrupt_db_writer

${pm2EnsureRestartDbWriterShell(cwd).trim()}

wait_pm2_online DuckClaw-DB-Writer 45 || echo "PM2_WARN: DuckClaw-DB-Writer not online yet"

${pm2EnsureRestartHeartbeatShell(cwd).trim()}

wait_pm2_online DuckClaw-Heartbeat 30 || echo "PM2_WARN: DuckClaw-Heartbeat not online yet"

if [ -n "\${DUCKCLAW_GATEWAY_SYSTEMD_UNIT:-}" ]; then
  for n in DuckClaw-Gateway duckclaw-gateway DuckClaw-API; do
    pm2 delete "\$n" 2>/dev/null || true
  done
  systemctl restart "\$DUCKCLAW_GATEWAY_SYSTEMD_UNIT"
  wait_gateway_health 60 || true
else
  ${pm2EnsureRestartGatewayShell(cwd).trim()}

  wait_pm2_online DuckClaw-Gateway 45 || wait_pm2_online duckclaw-gateway 45 || {

    echo "PM2_FALLBACK: starting DuckClaw-Gateway"

    pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway

    wait_pm2_online DuckClaw-Gateway 30 || exit 1

  }
fi

wait_gateway_health 60 || true

pm2 save 2>/dev/null || true

pm2 list

echo "STACK_RESTART_CORE_OK"

`;

  const proc = await runShell(cwd, shell, 180_000);

  return normalizeOpsResult({

    op_id: 'restart_stack',

    exit_code: proc.exit_code,

    stdout: proc.stdout,

    stderr: proc.stderr,

    executed_via: 'local',

  });

}


