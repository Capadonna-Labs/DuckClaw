import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayLongFetch, gatewayProxyHeaders } from '@/lib/gatewayProxy';

/** ComfyUI (~3–4 min) + cold start worker; margen para MCP omitido en visual_generation */
export const maxDuration = 600;
export const dynamic = 'force-dynamic';

const GATEWAY_CHAT_TIMEOUT_MS = 590_000;

/** Proxy al chat admin del gateway (JSON o SSE si stream=true). */
export async function POST(req: NextRequest) {
  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  if (!key) {
    return NextResponse.json({ detail: 'DUCKCLAW_ADMIN_API_KEY no configurada' }, { status: 503 });
  }

  const actor = req.headers.get('x-duckclaw-actor');
  const bodyText = await req.text();
  let wantsStream = false;
  try {
    const parsed = JSON.parse(bodyText) as { stream?: boolean };
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
  if (actor) headers['X-Duckclaw-Actor'] = actor;

  const target = `${base}/api/v1/admin/playground/chat`;

  try {
    const res = await gatewayLongFetch(target, {
      method: 'POST',
      headers,
      body: bodyText,
      cache: 'no-store',
      signal: AbortSignal.timeout(GATEWAY_CHAT_TIMEOUT_MS),
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
          ? 'El chat superó el tiempo máximo del proxy (generación de imagen puede tardar ~4 min). Reintenta o usa /gen/image.'
          : msg,
        hint: '¿Está corriendo DuckClaw-Gateway? Tras actualizar código, reinicia gateway y admin (pnpm dev).',
        code: isTimeout ? 'proxy_timeout' : 'gateway_unreachable',
      },
      { status: isTimeout ? 504 : 502 }
    );
  }
}
