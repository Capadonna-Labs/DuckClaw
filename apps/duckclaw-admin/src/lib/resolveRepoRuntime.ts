import { existsSync } from 'fs';
import { join } from 'path';
import { repoRoot } from '@/lib/localOps';

/** Python del venv del monorepo (mismo criterio que ecosystem.runtime.cjs). */
export function resolveRepoPython(root = repoRoot()): string {
  const fromEnv = process.env.DUCKCLAW_PM2_PYTHON?.trim();
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  const candidates = [
    join(root, '.venv', 'Scripts', 'pythonw.exe'),
    join(root, '.venv', 'Scripts', 'python.exe'),
    join(root, '.venv', 'bin', 'python3'),
    join(root, '.venv', 'bin', 'python'),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return 'python3';
}

/** Ruta absoluta a `uv` cuando PM2 no hereda ~/.local/bin en PATH. */
export function resolveUvBin(): string {
  const fromEnv = process.env.DUCKCLAW_UV_BIN?.trim();
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  const home = process.env.HOME?.trim() || '/root';
  const candidates = [
    join(home, '.local', 'bin', 'uv'),
    '/usr/local/bin/uv',
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return 'uv';
}

function resolveVenvScript(name: string, root = repoRoot()): string | null {
  const candidates = [
    join(root, '.venv', 'bin', name),
    join(root, '.venv', 'Scripts', `${name}.exe`),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

/** Equivalente a `uv run …` con fallback al venv cuando `uv` no está en PATH (PM2 admin). */
export function buildUvRunArgv(args: string[], root = repoRoot()): string[] {
  if (args[0] === 'python') {
    const py = resolveRepoPython(root);
    if (py !== 'python3') return [py, ...args.slice(1)];
  }
  const script = resolveVenvScript(args[0], root);
  if (script) return [script, ...args.slice(1)];
  const uv = resolveUvBin();
  if (uv !== 'uv' && existsSync(uv)) {
    return [uv, 'run', ...args];
  }
  return [uv, 'run', ...args];
}
