import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'], requireCsrf: true });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const target = `${base}/api/v1/admin/agents/spawn-package/import`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;
  const contentType = req.headers.get('content-type');
  if (contentType) headers['Content-Type'] = contentType;

  try {
    const res = await fetch(target, {
      method: 'POST',
      headers,
      body: await req.arrayBuffer(),
      cache: 'no-store',
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
