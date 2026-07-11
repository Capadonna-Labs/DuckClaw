import { spawn } from 'child_process';
import { join } from 'path';
import { HOST_ONLY_OPS, type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { opsSubprocessEnv } from '@/lib/opsSubprocessEnv';
import {
  GATEWAY_PM2_CANDIDATES,
  resolveGatewayPm2Name,
  substitutePm2NamesInArgv,
} from '@/lib/pm2AppResolve';
import { pm2RecycleDbWriterShell, pm2RecycleGatewayShell } from '@/lib/pm2Recycle';
import { runStackRecoverLocal } from '@/lib/stackRecover';
import { runStackStartLocal } from '@/lib/stackStart';
import { runTelegramIngressStartLocal } from '@/lib/telegramIngressStart';

export { HOST_ONLY_OPS };

/** Ops de integración: ejecutables pero no listados en comandos generales de plataforma. */
export const INTEGRATION_ONLY_OPS = new Set([
  'start_telegram_ingress',
  'build_edge_native',
  'pm2_start_edge_streamlit',
  'pm2_restart_edge_streamlit',
  'pm2_logs_edge_streamlit',
]);

export const OPS_ALLOWLIST: Record<string, { label: string; argv: string[] }> = {
  pm2_list: { label: 'PM2 — listar procesos', argv: ['pm2', 'list'] },
  pm2_status: { label: 'PM2 — estado', argv: ['pm2', 'status'] },
  pm2_restart_gateway: {
    label: 'Reiniciar DuckClaw-Gateway',
    argv: ['__pm2_recycle_gateway__'],
  },
  pm2_restart_db_writer: {
    label: 'Reiniciar DuckClaw-DB-Writer',
    argv: ['__pm2_recycle_db_writer__'],
  },
  pm2_start_db_writer: {
    label: 'Iniciar DuckClaw-DB-Writer',
    argv: ['__pm2_recycle_db_writer__'],
  },
  pm2_start_gateway: {
    label: 'Iniciar DuckClaw-Gateway',
    argv: ['__pm2_recycle_gateway__'],
  },
  start_stack: {
    label: 'Iniciar plataforma',
    argv: ['__start_stack__'],
  },
  restart_stack: {
    label: 'Reiniciar plataforma (migrate + PM2)',
    argv: ['__restart_stack__'],
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
  pm2_start_comfyui: {
    label: 'Iniciar ComfyUI',
    argv: ['pm2', 'start', 'config/ecosystem.comfyui.config.cjs', '--update-env'],
  },
  pm2_restart_comfyui: {
    label: 'Reiniciar ComfyUI',
    argv: ['pm2', 'restart', 'ComfyUI', '--update-env'],
  },
  pm2_logs_comfyui: {
    label: 'Últimas líneas log ComfyUI',
    argv: ['pm2', 'logs', 'ComfyUI', '--lines', '40', '--nostream'],
  },
  build_edge_native: {
    label: 'Compilar libedgecore (native/)',
    argv: ['bash', 'scripts/build_edge_native.sh'],
  },
  pm2_start_edge_streamlit: {
    label: 'Iniciar dashboard Edge (Streamlit)',
    argv: ['pm2', 'start', 'config/ecosystem.edge-devices.config.cjs', '--update-env'],
  },
  pm2_restart_edge_streamlit: {
    label: 'Reiniciar dashboard Edge (Streamlit)',
    argv: ['pm2', 'restart', 'Edge-Streamlit', '--update-env'],
  },
  pm2_logs_edge_streamlit: {
    label: 'Últimas líneas log Edge Streamlit',
    argv: ['pm2', 'logs', 'Edge-Streamlit', '--lines', '40', '--nostream'],
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

const PM2_SHELL_OPS: Record<string, (root: string) => string> = {
  pm2_restart_gateway: pm2RecycleGatewayShell,
  pm2_start_gateway: pm2RecycleGatewayShell,
  pm2_restart_db_writer: pm2RecycleDbWriterShell,
  pm2_start_db_writer: pm2RecycleDbWriterShell,
};

function runShellOp(opId: string, shell: string): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
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

function runArgvOp(opId: string, argv: string[]): Promise<NormalizedOpsRunResult> {
  const cwd = repoRoot();
  return new Promise((resolve, reject) => {
    const proc = spawn(argv[0], argv.slice(1), {
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

export function isLocalOpId(opId: string): boolean {
  return opId in OPS_ALLOWLIST;
}

export function listOpsCommands() {
  return {
    commands: Object.entries(OPS_ALLOWLIST)
      .filter(([id]) => !INTEGRATION_ONLY_OPS.has(id))
      .map(([id, v]) => ({
      id,
      label: v.label,
      argv: v.argv,
    })),
  };
}

export async function runOpsLocal(opId: string): Promise<NormalizedOpsRunResult> {
  if (opId === 'start_stack') {
    return runStackStartLocal();
  }
  if (opId === 'restart_stack') {
    return runStackRecoverLocal();
  }
  if (opId === 'start_telegram_ingress') {
    return runTelegramIngressStartLocal();
  }
  const entry = OPS_ALLOWLIST[opId];
  if (!entry) {
    throw new Error(`Comando no permitido: ${opId}`);
  }
  const shellBuilder = PM2_SHELL_OPS[opId];
  if (shellBuilder) {
    return runShellOp(opId, shellBuilder(repoRoot()));
  }
  if (opId === 'pm2_logs_gateway') {
    const cwd = repoRoot();
    const name = await resolveGatewayPm2Name(cwd);
    const argv = substitutePm2NamesInArgv(entry.argv, name, GATEWAY_PM2_CANDIDATES);
    return runArgvOp(opId, argv);
  }
  return runArgvOp(opId, entry.argv);
}
