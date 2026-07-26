import { execFile } from 'child_process';
import { promisify } from 'util';
import { type NormalizedOpsRunResult, normalizeOpsResult } from '@/lib/formatOpsOutput';
import { applyDesktopEnvToProcessEnv } from '@/lib/desktopEnvFile';

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

/** Desktop restart: stop sidecar only; Tauri respawns bundled binary on next app open. */
export async function runStackRecoverDesktop(): Promise<NormalizedOpsRunResult> {
  applyDesktopEnvToProcessEnv();
  const chunks: string[] = ['── Modo desktop lite (sin PM2/duckops) ──\n'];

  if (process.platform === 'win32') {
    try {
      await execFileAsync('taskkill', ['/F', '/IM', 'duckclaw_backend.exe'], { windowsHide: true });
      chunks.push('── Deteniendo duckclaw_backend.exe ──\nOK\n');
    } catch {
      chunks.push('── Deteniendo duckclaw_backend.exe ──\n(no estaba en ejecución)\n');
    }
    await waitSidecarProcessesGone();
  }

  chunks.push(
    '\nCierra DuckClaw por completo y ábrelo de nuevo para reiniciar gateway y admin embebidos.\n',
    'Tus datos en %LOCALAPPDATA%\\DuckClaw\\ (db, desktop.env) se conservan.\n',
    'Para actualizaciones de app usa el banner «Actualizar y reiniciar» cuando esté disponible.\n'
  );

  return normalizeOpsResult({
    op_id: 'restart_stack',
    exit_code: 0,
    stdout: chunks.join('\n'),
    stderr: '',
    executed_via: 'desktop',
    ok: true,
  });
}
