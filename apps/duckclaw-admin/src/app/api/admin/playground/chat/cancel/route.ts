import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

/** Cancel cooperativo: timeout corto para no colgar detrás del turno SSE activo. */
export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req);
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin key no configurados' }, { status: 503 });
  }

  const body = await req.text();
  const target = `${base}/api/v1/admin/playground/chat/cancel`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, 'Content-Type': 'application/json' });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await fetch(target, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(8_000),
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'fetch failed';
    return NextResponse.json(
      { detail: `Cancel no alcanzó el gateway a tiempo: ${msg}`, code: 'cancel_timeout' },
      { status: 504 }
    );
  }
}
