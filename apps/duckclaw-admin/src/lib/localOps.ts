import { spawn } from 'child_process';
import { join } from 'path';

export const OPS_ALLOWLIST: Record<string, { label: string; argv: string[] }> = {
  pm2_list: { label: 'PM2 — listar procesos', argv: ['pm2', 'list'] },
  pm2_status: { label: 'PM2 — estado', argv: ['pm2', 'status'] },
  pm2_restart_gateway: {
    label: 'Reiniciar DuckClaw-Gateway',
    argv: ['pm2', 'restart', 'DuckClaw-Gateway', '--update-env'],
  },
  pm2_restart_db_writer: {
    label: 'Reiniciar DuckClaw-DB-Writer',
    argv: ['pm2', 'restart', 'DuckClaw-DB-Writer', '--update-env'],
  },
  pm2_logs_gateway: {
    label: 'Últimas líneas log Gateway',
    argv: ['pm2', 'logs', 'DuckClaw-Gateway', '--lines', '40', '--nostream'],
  },
  doctor: { label: 'Diagnóstico local (doctor.py)', argv: ['uv', 'run', 'python', 'scripts/doctor.py'] },
  bootstrap_dbs: {
    label: 'Bootstrap DuckDB',
    argv: ['uv', 'run', 'python', 'scripts/bootstrap_dbs.py'],
  },
};

export function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

export function listOpsCommands() {
  return {
    commands: Object.entries(OPS_ALLOWLIST).map(([id, v]) => ({
      id,
      label: v.label,
      argv: v.argv,
    })),
  };
}

export function runOpsLocal(opId: string): Promise<{
  ok: boolean;
  op_id: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  executed_via: 'local';
}> {
  const entry = OPS_ALLOWLIST[opId];
  if (!entry) {
    return Promise.reject(new Error(`Comando no permitido: ${opId}`));
  }
  const cwd = repoRoot();
  return new Promise((resolve, reject) => {
    const proc = spawn(entry.argv[0], entry.argv.slice(1), {
      cwd,
      env: process.env,
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
      reject(new Error('Timeout ejecutando comando (90s)'));
    }, 90_000);
    proc.on('close', (code) => {
      clearTimeout(timer);
      const exit_code = code ?? 1;
      resolve({
        ok: exit_code === 0,
        op_id: opId,
        exit_code,
        stdout: stdout.slice(-12_000),
        stderr: stderr.slice(-8_000),
        executed_via: 'local',
      });
    });
    proc.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}
