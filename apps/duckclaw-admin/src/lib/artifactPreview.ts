/** Utilidades compartidas cliente/servidor (sin Node fs). */

export function parseArtifactIdFromPath(filePath?: string | null): string | null {
  if (!filePath?.trim()) return null;
  const m = filePath.trim().match(/artifacts[/\\]([0-9a-f-]{36})\.(png|jpe?g|webp)$/i);
  return m ? m[1] : null;
}

export function artifactPreviewApiPath(tenantId: string, artifactId: string): string {
  return `/api/admin/artifacts/${encodeURIComponent(tenantId)}/${encodeURIComponent(artifactId)}`;
}
