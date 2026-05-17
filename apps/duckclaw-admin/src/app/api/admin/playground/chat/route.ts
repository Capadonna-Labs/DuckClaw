import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

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
    const res = await fetch(target, {
      method: 'POST',
      headers,
      body: bodyText,
      cache: 'no-store',
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
    return NextResponse.json(
      {
        detail: e instanceof Error ? e.message : 'Error de red al gateway',
        hint: '¿Está corriendo DuckClaw-Gateway? Tras actualizar código, reinicia el gateway (Overview → Operaciones).',
      },
      { status: 502 }
    );
  }
}
