import { execFile, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const PM2_JLIST_MAX_BUFFER = 4 * 1024 * 1024;

function npmGlobalRoots(): string[] {
  const roots: string[] = [];
  const appdata = (process.env.APPDATA || '').trim();
  if (appdata) roots.push(path.join(appdata, 'npm'));
  const prefix = (process.env.NPM_PREFIX || '').trim();
  if (prefix) roots.push(prefix);
  return roots;
}

/** Windows: ``pm2`` en PATH suele ser ``pm2.ps1``; Node solo ejecuta bien vía ``node …/pm2/bin/pm2``. */
export function resolvePm2CliScript(): string | null {
  for (const root of npmGlobalRoots()) {
    const candidate = path.join(root, 'node_modules', 'pm2', 'bin', 'pm2');
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function pm2JlistArgv(): [string, string[]] | null {
  const pm2Script = resolvePm2CliScript();
  if (pm2Script) return [process.execPath, [pm2Script, 'jlist']];
  if (process.platform !== 'win32') return ['pm2', ['jlist']];
  return null;
}

const execOpts = (timeoutMs: number) => ({
  encoding: 'utf8' as const,
  timeout: timeoutMs,
  maxBuffer: PM2_JLIST_MAX_BUFFER,
  windowsHide: true,
});

export function pm2JlistStdoutSync(timeoutMs = 8_000): string | null {
  const argv = pm2JlistArgv();
  if (!argv) return null;
  const [bin, args] = argv;
  try {
    return execFileSync(bin, args, execOpts(timeoutMs));
  } catch {
    return null;
  }
}

export async function pm2JlistStdout(timeoutMs = 8_000): Promise<string | null> {
  const argv = pm2JlistArgv();
  if (!argv) return null;
  const [bin, args] = argv;
  try {
    const { stdout } = await execFileAsync(bin, args, execOpts(timeoutMs));
    return stdout;
  } catch {
    return null;
  }
}

export function parsePm2Jlist(stdout: string | null): unknown[] {
  if (!stdout?.trim()) return [];
  try {
    const parsed = JSON.parse(stdout) as unknown;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
