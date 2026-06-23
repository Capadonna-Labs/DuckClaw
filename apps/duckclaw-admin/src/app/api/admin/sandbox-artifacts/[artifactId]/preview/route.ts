import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

type Ctx = { params: { artifactId: string } };

/** Proxy preview de artefacto sandbox (imagen binaria o JSON de texto/tabular). */
export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const artifactId = encodeURIComponent(ctx.params.artifactId || '');
  const url = new URL(req.url);
  const chatId = url.searchParams.get('chat_id') || '';
  if (!chatId.trim()) {
    return NextResponse.json({ detail: 'chat_id requerido' }, { status: 400 });
  }

  const target = `${base}/api/v1/admin/sandbox/artifacts/${artifactId}/preview?chat_id=${encodeURIComponent(chatId)}`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, Accept: '*/*' });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await fetch(target, { method: 'GET', headers, cache: 'no-store' });
    const contentType = res.headers.get('content-type') || 'application/octet-stream';
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'private, no-store',
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
