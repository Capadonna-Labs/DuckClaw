import assert from 'node:assert/strict';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const prevExtension = process.env.DUCKCLAW_EXTENSION_ROOT;
const prevRepo = process.env.DUCKCLAW_REPO_ROOT;
const prevAdminRepo = process.env.DUCKCLAW_ADMIN_REPO_ROOT;

function withEnv(env: Record<string, string | undefined>, fn: () => void) {
  for (const [k, v] of Object.entries(env)) {
    if (v == null) delete process.env[k];
    else process.env[k] = v;
  }
  try {
    fn();
  } finally {
    if (prevExtension == null) delete process.env.DUCKCLAW_EXTENSION_ROOT;
    else process.env.DUCKCLAW_EXTENSION_ROOT = prevExtension;
    if (prevRepo == null) delete process.env.DUCKCLAW_REPO_ROOT;
    else process.env.DUCKCLAW_REPO_ROOT = prevRepo;
    if (prevAdminRepo == null) delete process.env.DUCKCLAW_ADMIN_REPO_ROOT;
    else process.env.DUCKCLAW_ADMIN_REPO_ROOT = prevAdminRepo;
  }
}

const vaultRoot = join(tmpdir(), `duckclaw-vault-${Date.now()}`);
mkdirSync(join(vaultRoot, 'db', 'private', 'default', 'artifacts'), { recursive: true });
writeFileSync(join(vaultRoot, 'db', 'private', 'default', 'artifacts', '.keep'), '');

withEnv(
  {
    DUCKCLAW_EXTENSION_ROOT: undefined,
    DUCKCLAW_ADMIN_REPO_ROOT: undefined,
    DUCKCLAW_REPO_ROOT: vaultRoot,
  },
  () => {
    delete require.cache[require.resolve('./extensionRoot')];
    const { resolveProductDbRoot } = require('./extensionRoot') as typeof import('./extensionRoot');
    assert.equal(resolveProductDbRoot(), vaultRoot);
  }
);

rmSync(vaultRoot, { recursive: true, force: true });
assert.ok(!existsSync(vaultRoot));

console.log('extensionRoot.test.ts OK');
