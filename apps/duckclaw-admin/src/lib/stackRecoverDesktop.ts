import { execFile, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

import {
  applyDesktopEnvToProcessEnv,
  desktopBackendExePath,
  readDesktopEnvFile,
} from '@/lib/desktopEnvFile';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';

const execFileAsync = promisify(execFile);

async function waitSidecarProcessesGone(maxMs = 15_000): Promise<void> {
  if (process.platform !== 'win32') return;
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    try {
      const { stdout } = await execFileAsync(
        'tasklist',
        ['/FI', 'IMAGENAME eq duckclaw_backend.exe', '/FO', 'CSV', '/NH'],
        { windowsHide: true }
      );
      if (!stdout.toLowerCase().includes('duckclaw_backend.exe')) return;
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function gatewayHealthBase(): string {
  const fromEnv = (process.env.DUCKCLAW_GATEWAY_URL || '').trim();
  if (fromEnv) return fromEnv.replace(/\/$/, '');
  const fileEnv = readDesktopEnvFile();
  const fromFile = (fileEnv.DUCKCLAW_GATEWAY_URL || '').trim();
  if (fromFile) return fromFile.replace(/\/$/, '');
  const host =
    (process.env.DUCKCLAW_GATEWAY_HOST || fileEnv.DUCKCLAW_GATEWAY_HOST || '127.0.0.1').trim() ||
    '127.0.0.1';
  const port =
    (process.env.DUCKCLAW_GATEWAY_PORT || fileEnv.DUCKCLAW_GATEWAY_PORT || '8000').trim() || '8000';
  return `http://${host}:${port}`;
}

async function waitGatewayHealth(base: string, timeoutMs = 90_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  const url = `${base.replace(/\/$/, '')}/health`;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, {
        cache: 'no-store',
        signal: AbortSignal.timeout(5_000),
      });
      if (res.ok) return true;
    } catch {
      /* sigue reintentando */
    }
    await new Promise((resolve) => setTimeout(resolve, 1_500));
  }
  return false;
}

function startDesktopSidecar(exe: string): void {
  applyDesktopEnvToProcessEnv();
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    LITE_MODE: '1',
    DUCKCLAW_SPAWN_PROFILE: '1',
  };
  if (!(env.DUCKCLAW_DISABLE_DOTENV || '').trim()) {
    env.DUCKCLAW_DISABLE_DOTENV = '1';
  }

  const child = spawn(exe, [], {
    cwd: path.dirname(exe),
    env,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  child.unref();
}

/**
 * Desktop lite: mata y vuelve a arrancar duckclaw_backend.exe (sin PM2).
 * El BFF Node debe hacer el relaunch; Tauri no respawnea el sidecar mientras la app sigue abierta.
 */
export async function runStackRecoverDesktop(): Promise<NormalizedOpsRunResult> {
  applyDesktopEnvToProcessEnv();
  const chunks: string[] = ['── Modo desktop lite (sin PM2/duckops) ──\n'];
  const exe = desktopBackendExePath();

  if (!exe || !fs.existsSync(exe)) {
    return normalizeOpsResult({
      op_id: 'restart_stack',
      exit_code: 1,
      stdout: chunks.join('\n'),
      stderr:
        `No se encontró duckclaw_backend.exe en %LOCALAPPDATA%\\DuckClaw\\. ` +
        `Copia el sidecar o reinstala DuckClaw.`,
      executed_via: 'desktop',
      ok: false,
    });
  }

  if (process.platform === 'win32') {
    try {
      await execFileAsync('taskkill', ['/F', '/IM', 'duckclaw_backend.exe'], { windowsHide: true });
      chunks.push('── Deteniendo duckclaw_backend.exe ──\nOK\n');
    } catch {
      chunks.push('── Deteniendo duckclaw_backend.exe ──\n(no estaba en ejecución)\n');
    }
    await waitSidecarProcessesGone();
  }

  await new Promise((resolve) => setTimeout(resolve, 800));

  try {
    startDesktopSidecar(exe);
    chunks.push(`── Arrancando sidecar ──\n${exe}\n`);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return normalizeOpsResult({
      op_id: 'restart_stack',
      exit_code: 1,
      stdout: chunks.join('\n'),
      stderr: `No se pudo arrancar el sidecar: ${msg}`,
      executed_via: 'desktop',
      ok: false,
    });
  }

  const healthBase = gatewayHealthBase();
  chunks.push(`── Esperando ${healthBase}/health ──\n`);
  const healthy = await waitGatewayHealth(healthBase);
  if (healthy) {
    chunks.push('Gateway listo.\n');
  } else {
    chunks.push('⚠ /health no respondió en 90s.\n');
  }

  return normalizeOpsResult({
    op_id: 'restart_stack',
    exit_code: healthy ? 0 : 2,
    stdout: chunks.join('\n'),
    stderr: healthy ? '' : `Sidecar no respondió en ${healthBase}.`,
    executed_via: 'desktop',
    ok: healthy,
  });
}
