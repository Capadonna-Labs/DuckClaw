import { spawn, type ChildProcess } from 'child_process';
import { repoRoot } from '@/lib/localOps';
import { parsePm2LogAppsParam } from '@/lib/pm2LogApps';
import { listRunningPm2AppNames } from '@/lib/pm2RunningApps';

export function startPm2LogsStream(
  appsParam: string | null,
  signal: AbortSignal
): { stream: ReadableStream<Uint8Array>; kill: () => void } {
  const parsed = parsePm2LogAppsParam(appsParam);
  if (!parsed.ok) {
    throw new Error(parsed.error);
  }

  const running = new Set(listRunningPm2AppNames());
  const missing = parsed.names.filter((name) => !running.has(name));
  if (missing.length > 0) {
    throw new Error(
      `Sin proceso PM2 en este host: ${missing.join(', ')}. MLX-Vision/ComfyUI suelen correr en la Mac GPU.`
    );
  }

  let proc: ChildProcess | null = null;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const names = parsed.names.join(',');
      proc = spawn('pm2', ['logs', names, '--raw'], {
        cwd: repoRoot(),
        env: process.env,
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const onChunk = (chunk: Buffer) => {
        try {
          controller.enqueue(new Uint8Array(chunk));
        } catch {
          /* closed */
        }
      };

      proc.stdout?.on('data', onChunk);
      proc.stderr?.on('data', onChunk);

      proc.on('error', (err) => {
        controller.error(err);
      });

      proc.on('close', () => {
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      });

      const onAbort = () => {
        proc?.kill('SIGTERM');
        try {
          controller.close();
        } catch {
          /* ignore */
        }
      };

      if (signal.aborted) {
        onAbort();
        return;
      }
      signal.addEventListener('abort', onAbort, { once: true });
    },
    cancel() {
      proc?.kill('SIGTERM');
      proc = null;
    },
  });

  return {
    stream,
    kill: () => proc?.kill('SIGTERM'),
  };
}
