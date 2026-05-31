import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayLongFetch, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const maxDuration = 480;
export const dynamic = 'force-dynamic';

/** Proxy generación ComfyUI (puede tardar varios minutos). */
export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  if (!key) {
    return NextResponse.json({ detail: 'DUCKCLAW_ADMIN_API_KEY no configurada' }, { status: 503 });
  }

  const bodyText = await req.text();
  const headers = gatewayProxyHeaders({
    'Content-Type': 'application/json',
    'X-Admin-Key': key,
  });
  headers['X-Duckclaw-Actor'] = auth.actor;

  const target = `${base}/api/v1/admin/comfyui/generate`;

  try {
    const res = await gatewayLongFetch(target, {
      method: 'POST',
      headers,
      body: bodyText,
      cache: 'no-store',
      signal: AbortSignal.timeout(470_000),
    });
    if (res.status === 404) {
      return NextResponse.json(
        {
          detail:
            'El Gateway no expone /comfyui/generate (código viejo). En el Mac: pm2 restart DuckClaw-Gateway --update-env',
          code: 'gateway_stale',
        },
        { status: 503 }
      );
    }
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    return NextResponse.json(
      {
        detail: e instanceof Error ? e.message : 'Error de red al gateway',
        hint: '¿ComfyUI y DuckClaw-Gateway están en línea?',
      },
      { status: 502 }
    );
  }
}
