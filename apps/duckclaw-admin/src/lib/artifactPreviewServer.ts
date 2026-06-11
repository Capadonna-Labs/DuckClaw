import { existsSync } from 'fs';
import { appendFile, readFile } from 'fs/promises';
import { join, resolve } from 'path';
import { repoRoot } from '@/lib/localOps';

/** Misma prioridad que ``vaults.db_root()`` en el gateway (Capadonna antes que monorepo). */
export function resolveProductDbRoot(): string {
  const capadonnaRoot = process.env.CAPADONNA_DRILLER_ROOT?.trim();
  if (capadonnaRoot) return capadonnaRoot;
  return repoRoot();
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const MIME: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
};

async function agentDebugLog(
  location: string,
  message: string,
  data: Record<string, unknown>,
  hypothesisId: string
): Promise<void> {
  // #region agent log
  try {
    const logPath = resolve(resolveProductDbRoot(), 'debug-480705.log');
    const payload = {
      sessionId: '480705',
      timestamp: Date.now(),
      location,
      message,
      data,
      hypothesisId,
      runId: 'pre-fix',
    };
    await appendFile(logPath, `${JSON.stringify(payload)}\n`, 'utf8');
  } catch {
    /* noop */
  }
  // #endregion
}

export async function readTenantArtifact(
  tenantId: string,
  artifactId: string
): Promise<{ bytes: Buffer; contentType: string } | null> {
  const tid = (tenantId || 'default').trim() || 'default';
  const aid = (artifactId || '').trim();
  if (!UUID_RE.test(aid)) return null;

  const productRoot = resolveProductDbRoot();
  const artifactsDir = resolve(productRoot, 'db', 'private', tid, 'artifacts');
  const privateRoot = resolve(productRoot, 'db', 'private');
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
    // #region agent log
    await agentDebugLog(
      'artifactPreviewServer.ts:readTenantArtifact',
      'artifact found',
      {
        tenantId: tid,
        artifactId: aid,
        productRoot,
        resolvedPath: resolved,
        byteLength: bytes.length,
      },
      'A'
    );
    // #endregion
    return { bytes, contentType: MIME[ext] || 'application/octet-stream' };
  }
  // #region agent log
  await agentDebugLog(
    'artifactPreviewServer.ts:readTenantArtifact',
    'artifact not found',
    {
      tenantId: tid,
      artifactId: aid,
      productRoot,
      artifactsDir,
      repoRootEnv: process.env.DUCKCLAW_REPO_ROOT ?? null,
      capadonnaRootEnv: process.env.CAPADONNA_DRILLER_ROOT ?? null,
    },
    'A'
  );
  // #endregion
  return null;
}
