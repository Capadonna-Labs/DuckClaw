import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

type Ctx = { params: { workerId: string } };

export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const workerId = encodeURIComponent(ctx.params.workerId || '');
  const target = `${base}/api/v1/admin/agents/${workerId}/spawn-package`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, Accept: '*/*' });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await fetch(target, { method: 'GET', headers, cache: 'no-store' });
    const contentType = res.headers.get('content-type') || 'application/zip';
    const disposition = res.headers.get('content-disposition');
    const body = await res.arrayBuffer();
    const outHeaders: Record<string, string> = {
      'Content-Type': contentType,
      'Cache-Control': 'private, no-store',
    };
    if (disposition) outHeaders['Content-Disposition'] = disposition;
    return new NextResponse(body, { status: res.status, headers: outHeaders });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
