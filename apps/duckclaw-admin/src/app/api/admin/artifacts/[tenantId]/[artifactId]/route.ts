import { NextRequest, NextResponse } from 'next/server';
import { readTenantArtifact } from '@/lib/artifactPreviewServer';
import { normalizeAdminRole } from '@/lib/roles';

export const dynamic = 'force-dynamic';

/** Sirve PNG/JPEG/WebP desde db/private/{tenant}/artifacts/{uuid}.* (solo admin UI local). */
export async function GET(
  req: NextRequest,
  ctx: { params: { tenantId: string; artifactId: string } }
) {
  const rawRole = req.headers.get('x-duckclaw-role');
  if (rawRole) {
    const role = normalizeAdminRole(rawRole);
    if (role !== 'admin' && role !== 'user') {
      return NextResponse.json({ detail: 'Rol inválido' }, { status: 403 });
    }
  }

  const { tenantId, artifactId } = ctx.params;
  const file = await readTenantArtifact(tenantId, artifactId);
  if (!file) {
    return NextResponse.json({ detail: 'Artefacto no encontrado' }, { status: 404 });
  }

  return new NextResponse(new Uint8Array(file.bytes), {
    status: 200,
    headers: {
      'Content-Type': file.contentType,
      'Cache-Control': 'private, max-age=3600',
    },
  });
}
