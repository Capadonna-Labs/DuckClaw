import { spawn, type ChildProcess } from 'child_process';
import { repoRoot } from '@/lib/localOps';
import { parsePm2LogAppsParam } from '@/lib/pm2LogApps';

export function startPm2LogsStream(
  appsParam: string | null,
  signal: AbortSignal
): { stream: ReadableStream<Uint8Array>; kill: () => void } {
  const parsed = parsePm2LogAppsParam(appsParam);
  if (!parsed.ok) {
    throw new Error(parsed.error);
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
