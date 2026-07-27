/** Tail journalctl for systemd-managed DuckClaw gateway. */

import { spawn } from 'child_process';

export function startSystemdGatewayLogStream(
  unit: string,
  signal: AbortSignal
): { stream: ReadableStream<Uint8Array>; kill: () => void } {
  const encoder = new TextEncoder();
  let child: ReturnType<typeof spawn> | null = null;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const push = (line: string) => {
        try {
          controller.enqueue(encoder.encode(`${line}\n`));
        } catch {
          /* closed */
        }
      };

      push(`[systemd] Gateway unit=${unit} (PM2 duplicate ignored when port held by systemd).`);

      child = spawn('journalctl', ['-u', unit, '-f', '-n', '120', '--no-pager'], {
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const onData = (chunk: Buffer) => {
        for (const line of chunk.toString('utf8').split(/\r?\n/)) {
          if (line.trim()) push(line);
        }
      };

      child.stdout?.on('data', onData);
      child.stderr?.on('data', onData);

      child.on('error', (err) => {
        push(`[systemd] journalctl error: ${err.message}`);
      });

      const onAbort = () => {
        child?.kill('SIGTERM');
        child = null;
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
      child?.kill('SIGTERM');
      child = null;
    },
  });

  return { stream, kill: () => signal.abort() };
}
