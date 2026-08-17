import { createHash } from 'crypto';
import fs from 'fs';
import path from 'path';

const DESKTOP_ENV_KEYS = [
  'DUCKCLAW_ADMIN_API_KEY',
  'DUCKCLAW_ADMIN_EMAIL',
  'DUCKCLAW_ADMIN_PASSWORD',
  'DUCKCLAW_DESKTOP_ADMIN_PASSWORD',
] as const;

function desktopEnvPath(): string | null {
  const explicit = (process.env.DUCKCLAW_DESKTOP_ENV_FILE || '').trim();
  if (explicit) return explicit;
  const localAppData = (process.env.LOCALAPPDATA || '').trim();
  if (!localAppData) return null;
  return path.join(localAppData, 'DuckClaw', 'desktop.env');
}

function parseDesktopEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
    const [key, ...rest] = trimmed.split('=');
    const val = rest.join('=').trim().replace(/^['"]|['"]$/g, '');
    out[key.trim()] = val;
  }
  return out;
}

function replaceDesktopEnvValue(content: string, key: string, value: string): string {
  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const line = `${key}=${value}`;
  const expression = new RegExp(`^\\s*${escapedKey}\\s*=.*$`, 'm');
  if (expression.test(content)) return content.replace(expression, line);
  const suffix = content && !content.endsWith('\n') ? '\n' : '';
  return `${content}${suffix}${line}\n`;
}

/** `%LOCALAPPDATA%\\DuckClaw\\desktop.env` — source of truth for desktop bundle. */
export function readDesktopEnvFile(): Record<string, string> {
  const file = desktopEnvPath();
  if (!file || !fs.existsSync(file)) return {};
  try {
    return parseDesktopEnv(fs.readFileSync(file, 'utf8'));
  } catch {
    return {};
  }
}

/** Updates only the bootstrap credentials in the local desktop environment file. */
export function updateDesktopAdminCredentials(email: string, password: string): boolean {
  const file = desktopEnvPath();
  const normalizedEmail = email.trim().toLowerCase();
  if (!file || !normalizedEmail || !password || /[\r\n]/.test(normalizedEmail + password)) return false;
  try {
    const current = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
    const withEmail = replaceDesktopEnvValue(current, 'DUCKCLAW_ADMIN_EMAIL', normalizedEmail);
    const next = replaceDesktopEnvValue(withEmail, 'DUCKCLAW_ADMIN_PASSWORD', password);
    fs.writeFileSync(file, next, { encoding: 'utf8', mode: 0o600 });
    return true;
  } catch {
    return false;
  }
}

export function desktopAdminApiKey(): string {
  const fromFile = readDesktopEnvFile().DUCKCLAW_ADMIN_API_KEY?.trim();
  if (fromFile) return fromFile;
  return (process.env.DUCKCLAW_ADMIN_API_KEY || '').trim();
}

export function desktopEnvKeyFingerprint(key: string): string {
  const trimmed = key.trim();
  if (!trimmed) return '';
  return createHash('sha256').update(trimmed).digest('hex').slice(0, 8);
}

export function desktopEnvSources(): {
  fromFile: boolean;
  filePath: string | null;
  keyFp: string;
} {
  const file = desktopEnvPath();
  const fileEnv = readDesktopEnvFile();
  const fromFile = Boolean(fileEnv.DUCKCLAW_ADMIN_API_KEY?.trim());
  const key = desktopAdminApiKey();
  return {
    fromFile,
    filePath: file,
    keyFp: desktopEnvKeyFingerprint(key),
  };
}

export function applyDesktopEnvToProcessEnv(): void {
  const fileEnv = readDesktopEnvFile();
  for (const [key, val] of Object.entries(fileEnv)) {
    const trimmed = (val || '').trim();
    if (trimmed) process.env[key] = trimmed;
  }
}

export function desktopBackendExePath(): string | null {
  const localAppData = (process.env.LOCALAPPDATA || '').trim();
  if (!localAppData) return null;
  return path.join(localAppData, 'DuckClaw', 'duckclaw_backend.exe');
}

export function desktopGatewayLogPath(): string | null {
  const localAppData = (process.env.LOCALAPPDATA || '').trim();
  if (!localAppData) return null;
  return path.join(localAppData, 'DuckClaw', 'gateway.log');
}

function loopbackGatewayUrl(raw: string): boolean {
  const v = raw.trim();
  return v.includes('127.0.0.1:8000') || v.includes('localhost:8000');
}

/** DuckClaw desktop sidecar: sin PM2 ni duckops en el host. */
export function isDesktopLiteMode(): boolean {
  if ((process.env.LITE_MODE || '').trim() === '1') return true;
  if ((process.env.DUCKCLAW_SPAWN_PROFILE || '').trim() === '1') return true;
  const fileEnv = readDesktopEnvFile();
  if (fileEnv.LITE_MODE === '1' || fileEnv.DUCKCLAW_SPAWN_PROFILE === '1') return true;
  if (!fileEnv.DUCKCLAW_ADMIN_API_KEY?.trim()) return false;

  const gatewayUrl =
    (process.env.DUCKCLAW_GATEWAY_URL || fileEnv.DUCKCLAW_GATEWAY_URL || '').trim();
  if (loopbackGatewayUrl(gatewayUrl)) return true;

  const exe = desktopBackendExePath();
  if (exe && fs.existsSync(exe)) return true;

  if (
    process.platform === 'win32' &&
    ((process.env.DUCKCLAW_DISABLE_DOTENV || fileEnv.DUCKCLAW_DISABLE_DOTENV || '').trim() === '1' ||
      fs.existsSync(path.join((process.env.LOCALAPPDATA || '').trim(), 'DuckClaw', 'desktop.env')))
  ) {
    return true;
  }
  return false;
}

/** PM2 vacío + credenciales desktop → tratar Gateway embebido como activo. */
export function shouldUseDesktopGatewayLogs(selectedApp: string | null | undefined): boolean {
  if (!selectedApp?.includes('DuckClaw-Gateway')) return false;
  if (isDesktopLiteMode()) return true;
  if (process.platform !== 'win32') return false;
  return Boolean(readDesktopEnvFile().DUCKCLAW_ADMIN_API_KEY?.trim());
}
