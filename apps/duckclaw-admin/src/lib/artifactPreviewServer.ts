import { existsSync } from 'fs';
import { readFile } from 'fs/promises';
import { join, resolve } from 'path';
import { repoRoot } from '@/lib/localOps';

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const MIME: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
};

export async function readTenantArtifact(
  tenantId: string,
  artifactId: string
): Promise<{ bytes: Buffer; contentType: string } | null> {
  const tid = (tenantId || 'default').trim() || 'default';
  const aid = (artifactId || '').trim();
  if (!UUID_RE.test(aid)) return null;

  const artifactsDir = resolve(repoRoot(), 'db', 'private', tid, 'artifacts');
  const privateRoot = resolve(repoRoot(), 'db', 'private');
  if (!artifactsDir.startsWith(privateRoot)) {
    return null;
  }

  for (const ext of ['png', 'webp', 'jpg', 'jpeg'] as const) {
    const candidate = join(artifactsDir, `${aid}.${ext}`);
    const resolved = resolve(candidate);
    if (resolved !== artifactsDir && !resolved.startsWith(`${artifactsDir}/`)) {
      continue;
    }
    if (!existsSync(resolved)) continue;
    const bytes = await readFile(resolved);
    return { bytes, contentType: MIME[ext] || 'application/octet-stream' };
  }
  return null;
}
