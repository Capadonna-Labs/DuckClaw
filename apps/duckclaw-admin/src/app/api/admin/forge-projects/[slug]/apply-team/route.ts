import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Ctx = { params: { slug: string } };

export async function POST(req: NextRequest, ctx: Ctx) {
  if ((req.headers.get('x-duckclaw-role') || 'admin') !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json(
      { detail: 'Gateway no configurado; reinicia DuckClaw-Gateway para aplicar equipo.' },
      { status: 503 }
    );
  }
  const slug = ctx.params.slug;
  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/forge-projects/${encodeURIComponent(slug)}/apply-team${url.search}`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, 'Content-Type': 'application/json' });
  const actor = req.headers.get('x-duckclaw-actor');
  if (actor) headers['X-Duckclaw-Actor'] = actor;
  try {
    const res = await fetch(target, { method: 'POST', headers, body: '{}', cache: 'no-store' });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : 'No se pudo contactar el gateway' },
      { status: 503 }
    );
  }
}
