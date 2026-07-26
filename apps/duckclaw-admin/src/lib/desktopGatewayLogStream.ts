/** PM2 log stream fallback for desktop lite (embedded sidecar, no pm2 logs). */

import fs from 'fs';
import { desktopGatewayLogPath } from '@/lib/desktopEnvFile';

function tailInitialLines(filePath: string, maxLines: number): string[] {
  if (!fs.existsSync(filePath)) return [];
  try {
    const text = fs.readFileSync(filePath, 'utf8');
    return text.split(/\r?\n/).filter(Boolean).slice(-maxLines);
  } catch {
    return [];
  }
}

export function startDesktopGatewayLogStream(
  signal: AbortSignal
): { stream: ReadableStream<Uint8Array>; kill: () => void } {
  let timer: ReturnType<typeof setInterval> | null = null;
  let watchTimer: ReturnType<typeof setInterval> | null = null;
  let offset = 0;
  const encoder = new TextEncoder();
  const logPath = desktopGatewayLogPath();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const push = (line: string) => {
        try {
          controller.enqueue(encoder.encode(`${line}\n`));
        } catch {
          /* closed */
        }
      };

      push('[desktop] Gateway embebido (duckclaw_backend). Sin PM2 en este equipo.');
      if (logPath) {
        push(`[desktop] Log: ${logPath}`);
        for (const line of tailInitialLines(logPath, 120)) push(line);
        try {
          if (fs.existsSync(logPath)) {
            offset = fs.statSync(logPath).size;
          }
        } catch {
          offset = 0;
        }
      } else {
        push('[desktop] Sin ruta de log local (%LOCALAPPDATA%\\DuckClaw\\gateway.log).');
      }

      const readNewLogBytes = () => {
        if (!logPath || !fs.existsSync(logPath)) return;
        try {
          const stat = fs.statSync(logPath);
          if (stat.size < offset) offset = 0;
          if (stat.size <= offset) return;
          const fd = fs.openSync(logPath, 'r');
          const len = stat.size - offset;
          const buf = Buffer.alloc(len);
          fs.readSync(fd, buf, 0, len, offset);
          fs.closeSync(fd);
          offset = stat.size;
          for (const line of buf.toString('utf8').split(/\r?\n/)) {
            if (line.trim()) push(line);
          }
        } catch {
          /* ignore read races */
        }
      };

      watchTimer = setInterval(readNewLogBytes, 1000);

      timer = setInterval(async () => {
        if (signal.aborted) return;
        try {
          const res = await fetch('http://127.0.0.1:8000/health', { cache: 'no-store' });
          push(`[health] ${new Date().toISOString()} HTTP ${res.status}`);
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'fetch failed';
          push(`[health] ${new Date().toISOString()} offline (${msg})`);
        }
      }, 15000);

      const onAbort = () => {
        if (timer) clearInterval(timer);
        if (watchTimer) clearInterval(watchTimer);
        timer = null;
        watchTimer = null;
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
      if (timer) clearInterval(timer);
      if (watchTimer) clearInterval(watchTimer);
      timer = null;
      watchTimer = null;
    },
  });

  return { stream, kill: () => signal.abort() };
}
