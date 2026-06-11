import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayLongFetch, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const maxDuration = 600;
export const dynamic = 'force-dynamic';

type Ctx = { params: { reportId: string } };

/** Proxy SSE de recarga de reportes custom. */
export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const reportId = encodeURIComponent(ctx.params.reportId || '');
  const target = `${base}/api/v1/admin/reports/${reportId}/stream`;

  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, Accept: 'text/event-stream' });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await gatewayLongFetch(target, {
      method: 'GET',
      headers,
      cache: 'no-store',
      signal: req.signal,
    });

    if (!res.body) {
      const text = await res.text();
      return new NextResponse(text, { status: res.status });
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('content-type') || 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
