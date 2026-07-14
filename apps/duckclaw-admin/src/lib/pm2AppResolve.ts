import { parsePm2Jlist, pm2JlistStdout } from '@/lib/pm2Jlist';

const PM2_JLIST_TIMEOUT_MS = 12_000;

export const GATEWAY_PM2_CANDIDATES = [
  'DuckClaw-Gateway',
  'duckclaw-gateway',
  'DuckClaw-API',
] as const;

export const DB_WRITER_PM2_CANDIDATES = ['DuckClaw-DB-Writer', 'duckclaw-db-writer'] as const;

async function pm2RegisteredNames(): Promise<Set<string>> {
  try {
    const stdout = await pm2JlistStdout(PM2_JLIST_TIMEOUT_MS);
    const apps = parsePm2Jlist(stdout) as { name?: string }[];
    return new Set(
      apps.map((a) => (a.name || '').trim()).filter((n): n is string => Boolean(n))
    );
  } catch {
    return new Set();
  }
}

export async function resolvePm2AppName(
  candidates: readonly string[],
  cwd: string,
  envVar?: string
): Promise<string> {
  const names = await pm2RegisteredNames();
  const preferred = envVar ? (process.env[envVar] || '').trim() : '';
  if (preferred && (!names.size || names.has(preferred))) return preferred;
  for (const candidate of candidates) {
    if (names.has(candidate)) return candidate;
  }
  return candidates[0];
}

export async function resolveGatewayPm2Name(cwd: string): Promise<string> {
  return resolvePm2AppName(GATEWAY_PM2_CANDIDATES, cwd, 'DUCKCLAW_PM2_PROCESS_NAME');
}

export async function resolveDbWriterPm2Name(cwd: string): Promise<string> {
  return resolvePm2AppName(DB_WRITER_PM2_CANDIDATES, cwd);
}

export function substitutePm2NamesInArgv(
  argv: string[],
  resolvedName: string,
  candidates: readonly string[]
): string[] {
  const replace = new Set(candidates);
  return argv.map((token) => (replace.has(token) ? resolvedName : token));
}
