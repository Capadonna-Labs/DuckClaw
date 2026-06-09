import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayLongFetch, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const maxDuration = 600;
export const dynamic = 'force-dynamic';

const GATEWAY_VOICE_TIMEOUT_MS = 590_000;

/** Proxy nota de voz → STT → agente → TTS (batch, sin Telegram). */
export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
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
    'X-Duckclaw-Actor': auth.actor,
  });

  const target = `${base}/api/v1/admin/playground/voice`;
  const timeoutSignal = AbortSignal.timeout(GATEWAY_VOICE_TIMEOUT_MS);
  const upstreamSignal =
    typeof AbortSignal.any === 'function'
      ? AbortSignal.any([req.signal, timeoutSignal])
      : req.signal.aborted
        ? req.signal
        : timeoutSignal;

  try {
    const res = await gatewayLongFetch(target, {
      method: 'POST',
      headers,
      body: bodyText,
      cache: 'no-store',
      signal: upstreamSignal,
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 502 });
  }
}
