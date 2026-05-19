import { spawn } from 'child_process';
import { join } from 'path';
import { HOST_ONLY_OPS, type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { runStackStartLocal } from '@/lib/stackStart';
import { runTelegramIngressStartLocal } from '@/lib/telegramIngressStart';

export { HOST_ONLY_OPS };

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
  pm2_start_db_writer: {
    label: 'Iniciar DuckClaw-DB-Writer',
    argv: ['pm2', 'start', 'config/ecosystem.db-writer.config.cjs', '--update-env'],
  },
  pm2_start_gateway: {
    label: 'Iniciar DuckClaw-Gateway',
    argv: ['pm2', 'start', 'config/ecosystem.api.config.cjs', '--only', 'DuckClaw-Gateway', '--update-env'],
  },
  start_stack: {
    label: 'Iniciar plataforma (PM2 + Telegram)',
    argv: ['__start_stack__'],
  },
  start_telegram_ingress: {
    label: 'Activar Tailscale (Telegram webhook)',
    argv: ['__start_telegram_ingress__'],
  },
  pm2_logs_gateway: {
    label: 'Últimas líneas log Gateway',
    argv: ['pm2', 'logs', 'DuckClaw-Gateway', '--lines', '40', '--nostream'],
  },
  pm2_start_mcp: {
    label: 'Iniciar DuckClaw-MCP',
    argv: ['pm2', 'start', 'config/ecosystem.mcp.config.cjs'],
  },
  pm2_restart_mcp: {
    label: 'Reiniciar DuckClaw-MCP',
    argv: ['pm2', 'restart', 'DuckClaw-MCP', '--update-env'],
  },
  pm2_logs_mcp: {
    label: 'Últimas líneas log MCP',
    argv: ['pm2', 'logs', 'DuckClaw-MCP', '--lines', '40', '--nostream'],
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

export function runOpsLocal(opId: string): Promise<NormalizedOpsRunResult> {
  if (opId === 'start_stack') {
    return runStackStartLocal();
  }
  if (opId === 'start_telegram_ingress') {
    return runTelegramIngressStartLocal();
  }
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
    proc.on('close', (code, signal) => {
      clearTimeout(timer);
      let exit_code = code ?? 1;
      if (code === null && signal) {
        const sigNum: Record<string, number> = {
          SIGINT: 2,
          SIGTERM: 15,
          SIGHUP: 1,
        };
        exit_code = sigNum[signal] ? -sigNum[signal]! : -1;
      }
      resolve(
        normalizeOpsResult({
          op_id: opId,
          exit_code,
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
