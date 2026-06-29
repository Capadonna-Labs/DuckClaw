import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import {
  mergeVoiceOfferRequestData,
  parseVoiceSessionFromSearchParams,
  voiceConnectHint,
  voiceInternalBase,
} from '@/lib/voiceRealtimeProxy';

export const dynamic = 'force-dynamic';

async function proxyVoiceOffer(req: NextRequest, method: 'POST' | 'PATCH') {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'], requireCsrf: false });
  if (!auth.ok) {
    return auth.response;
  }

  const voiceBase = voiceInternalBase();
  if (!voiceBase) {
    return NextResponse.json(
      { detail: `Servicio de voz no configurado (${voiceConnectHint()})` },
      { status: 503 }
    );
  }

  const bodyText = await req.text();
  let body: Record<string, unknown> = {};
  if (bodyText.trim()) {
    try {
      body = JSON.parse(bodyText) as Record<string, unknown>;
    } catch {
      return NextResponse.json({ detail: 'Cuerpo JSON inválido para offer WebRTC' }, { status: 400 });
    }
  }

  const session = parseVoiceSessionFromSearchParams(req.nextUrl.searchParams);
  if (method === 'POST') {
    body = mergeVoiceOfferRequestData(body, {
      ...session,
      actor_email: auth.actor,
    });
  }

  const target = `${voiceBase}/api/offer`;
  try {
    const upstream = await fetch(target, {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: req.signal,
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al servicio de voz';
    return NextResponse.json({ detail: msg }, { status: 502 });
  }
}

/** Proxy SDP offer → DuckClaw-Voice /api/offer (inyecta worker/chat/tenant). */
export async function POST(req: NextRequest) {
  return proxyVoiceOffer(req, 'POST');
}

/** Proxy ICE candidates → DuckClaw-Voice /api/offer PATCH. */
export async function PATCH(req: NextRequest) {
  return proxyVoiceOffer(req, 'PATCH');
}
