import { NextRequest, NextResponse } from 'next/server';
import { gatewayBase } from '@/lib/gatewayProxy';

export async function POST(req: NextRequest) {
  const base = gatewayBase();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  const body = await req.text();
  const res = await fetch(`${base}/api/v1/admin/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    cache: 'no-store',
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
  });
}
