import { repoRoot } from './localOps';

/** Same priority as ``vaults.db_root()`` in the gateway (extension before monorepo). */
export function resolveProductDbRoot(): string {
  const extensionRoot = process.env.DUCKCLAW_EXTENSION_ROOT?.trim();
  if (extensionRoot) return extensionRoot;
  return repoRoot();
}
