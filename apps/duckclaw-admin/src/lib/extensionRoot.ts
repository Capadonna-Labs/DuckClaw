import { existsSync } from 'fs';
import { join } from 'path';
import { repoRoot } from './localOps';

function hasPrivateDbTree(root: string): boolean {
  return existsSync(join(root, 'db', 'private'));
}

/** Same priority as ``vaults.db_root()`` in the gateway (extension before monorepo). */
export function resolveProductDbRoot(): string {
  const extensionRoot = process.env.DUCKCLAW_EXTENSION_ROOT?.trim();
  if (extensionRoot) return extensionRoot;
  // ponytail: admin PM2 often has DUCKCLAW_REPO_ROOT=vault tree but not DUCKCLAW_EXTENSION_ROOT.
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv && hasPrivateDbTree(fromEnv)) return fromEnv;
  return repoRoot();
}
