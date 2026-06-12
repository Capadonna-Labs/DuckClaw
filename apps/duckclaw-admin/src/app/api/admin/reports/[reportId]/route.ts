import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

const REPORT_HTML_CSP =
  "default-src 'self' https: data:; " +
  "script-src 'self' https: cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com cdn.tailwindcss.com 'unsafe-inline'; " +
  "style-src 'self' https: 'unsafe-inline'; " +
  "img-src 'self' https: data: blob:; " +
  "font-src 'self' https: data:; " +
  "connect-src 'self' https:; " +
  "frame-ancestors 'self'";

type Ctx = { params: { reportId: string } };

/** Proxy HTML del reporte custom desde el gateway. */
export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const reportId = encodeURIComponent(ctx.params.reportId || '');
  const url = new URL(req.url);
  const vault = url.searchParams.get('vault') || '';
  const target = `${base}/api/v1/admin/reports/${reportId}?vault=${encodeURIComponent(vault)}`;

  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key, Accept: 'text/html' });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await fetch(target, { method: 'GET', headers, cache: 'no-store' });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('content-type') || 'text/html; charset=utf-8',
        'Content-Security-Policy': REPORT_HTML_CSP,
        'X-Frame-Options': 'SAMEORIGIN',
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
