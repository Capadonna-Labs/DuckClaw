import { NextRequest, NextResponse } from 'next/server';
import { GATEWAY_CHAT_SSE_TIMEOUT_MS } from '@/lib/bffChatTimeout';
import { adminApiKey, gatewayBase, gatewayLongFetch, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

/** Next requires a literal (not imported) for route segment config. */
export const maxDuration = 3600;
export const dynamic = 'force-dynamic';

/** Proxy al chat admin del gateway (JSON o SSE si stream=true). */
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
  let wantsStream = false;
  try {
    const parsed = JSON.parse(bodyText) as { worker_id?: string; chat_id?: string; stream?: boolean; project_id?: string };
    wantsStream = Boolean(parsed.stream);
  } catch {
    /* cuerpo no JSON */
  }

  const headers = gatewayProxyHeaders({
    'Content-Type': 'application/json',
    'X-Admin-Key': key,
  });
  if (wantsStream) {
    headers.Accept = 'text/event-stream';
  }
  headers['X-Duckclaw-Actor'] = auth.actor;

  const target = `${base}/api/v1/admin/playground/chat`;

  const timeoutSignal = AbortSignal.timeout(GATEWAY_CHAT_SSE_TIMEOUT_MS);
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

    if (wantsStream && res.body) {
      return new NextResponse(res.body, {
        status: res.status,
        headers: {
          'Content-Type': res.headers.get('content-type') || 'text/event-stream',
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
      });
    }

    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    const isTimeout =
      msg.includes('timeout') ||
      msg.includes('Timeout') ||
      msg.includes('terminated') ||
      msg.includes('aborted');
    return NextResponse.json(
      {
        detail: isTimeout
          ? 'El chat superó el tiempo máximo del proxy (~30 min). Recarga el historial; el turno puede haber terminado en el servidor.'
          : msg,
        hint: '¿Está corriendo DuckClaw-Gateway? Tras actualizar código, reinicia gateway y admin (pnpm dev).',
        code: isTimeout ? 'proxy_timeout' : 'gateway_unreachable',
      },
      { status: isTimeout ? 504 : 502 }
    );
  }
}
