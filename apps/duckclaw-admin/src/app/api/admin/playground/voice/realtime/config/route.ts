import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

const OFFER_PATH = '/api/admin/playground/voice/realtime/offer';

/** Expose Pipecat realtime availability and same-origin signaling paths. */
export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json(
      {
        configured: false,
        available: false,
        transport: 'small_webrtc',
        signaling: { offer_url: OFFER_PATH },
        detail: 'Gateway o admin key no configurados',
      },
      { status: 503 }
    );
  }

  const chatId = (req.nextUrl.searchParams.get('chat_id') || '').trim();
  const qs = chatId ? `?chat_id=${encodeURIComponent(chatId)}` : '';

  try {
    const res = await fetch(`${base}/api/v1/admin/playground/config${qs}`, {
      headers: gatewayProxyHeaders({ 'X-Admin-Key': key, 'X-Duckclaw-Actor': auth.actor }),
      cache: 'no-store',
    });
    const payload = (await res.json()) as {
      realtime_voice?: { configured?: boolean; available?: boolean; transport?: string };
    };
    const realtime = payload.realtime_voice ?? {};
    return NextResponse.json({
      configured: Boolean(realtime.configured),
      available: Boolean(realtime.available),
      transport: realtime.transport || 'small_webrtc',
      signaling: { offer_url: OFFER_PATH },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error al consultar gateway';
    return NextResponse.json(
      {
        configured: false,
        available: false,
        transport: 'small_webrtc',
        signaling: { offer_url: OFFER_PATH },
        detail: msg,
      },
      { status: 502 }
    );
  }
}
