import { existsSync } from 'fs';
import { readFile } from 'fs/promises';
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

  const basenameCandidates: string[] = [];
  for (const prefix of ['', 'fal_'] as const) {
    for (const ext of ['png', 'webp', 'jpg', 'jpeg'] as const) {
      basenameCandidates.push(`${prefix}${aid}.${ext}`);
    }
  }

  for (const basename of basenameCandidates) {
    const candidate = join(artifactsDir, basename);
    const resolved = resolve(candidate);
    if (resolved !== artifactsDir && !resolved.startsWith(`${artifactsDir}/`)) {
      continue;
    }
    if (!existsSync(resolved)) continue;
    const bytes = await readFile(resolved);
    const ext = basename.split('.').pop()?.toLowerCase() || 'png';
    // #region agent log
    try {
      const { appendFileSync } = await import('fs');
      const logPath = join(productRoot, 'debug-480705.log');
      appendFileSync(
        logPath,
        `${JSON.stringify({
          sessionId: '480705',
          runId: 'post-fix',
          hypothesisId: 'H1-fal-prefix',
          location: 'artifactPreviewServer.ts:readTenantArtifact',
          message: 'artifact resolved',
          data: { tenantId: tid, artifactId: aid, resolvedBasename: basename },
          timestamp: Date.now(),
        })}\n`
      );
    } catch {
      /* debug log optional */
    }
    // #endregion
    return { bytes, contentType: MIME[ext] || 'application/octet-stream' };
  }
  // #region agent log
  try {
    const { appendFileSync } = await import('fs');
    const logPath = join(productRoot, 'debug-480705.log');
    appendFileSync(
      logPath,
      `${JSON.stringify({
        sessionId: '480705',
        runId: 'post-fix',
        hypothesisId: 'H1-fal-prefix',
        location: 'artifactPreviewServer.ts:readTenantArtifact',
        message: 'artifact not found',
        data: { tenantId: tid, artifactId: aid, tried: basenameCandidates.length },
        timestamp: Date.now(),
      })}\n`
    );
  } catch {
    /* debug log optional */
  }
  // #endregion
  return null;
}
