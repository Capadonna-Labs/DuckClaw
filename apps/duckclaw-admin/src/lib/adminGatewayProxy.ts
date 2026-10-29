import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

/** BFF proxy to one Gateway admin domain: the admin key stays server-side, the actor header carries the signed-in user. */
export async function proxyGatewayAdmin(
  req: NextRequest,
  gatewayPath: string,
  roles: ('admin' | 'user')[],
  label: string
) {
  const auth = await requireAdminRouteAuth(req, { roles });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json(
      { detail: `${label} requiere el Gateway configurado.`, code: 'gateway_stale' },
      { status: 503 }
    );
  }

  const url = new URL(req.url);
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;
  const contentType = req.headers.get('content-type');
  if (contentType) headers['Content-Type'] = contentType;

  const init: RequestInit = { method: req.method, headers, cache: 'no-store' };
  if (req.method !== 'GET' && req.method !== 'HEAD') init.body = await req.text();

  let response: Response;
  let text: string;
  try {
    response = await fetch(`${base}/api/v1/admin${gatewayPath}${url.search}`, init);
    text = await response.text();
  } catch {
    return NextResponse.json(
      { detail: `No se pudo contactar el Gateway para ${label}.`, code: 'gateway_unreachable' },
      { status: 503 }
    );
  }

  return new NextResponse(text, {
    status: response.status,
    headers: { 'Content-Type': response.headers.get('content-type') || 'application/json' },
  });
}
