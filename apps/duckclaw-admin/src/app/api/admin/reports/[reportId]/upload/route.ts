import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const dynamic = 'force-dynamic';

type Ctx = { params: { reportId: string } };

/** Proxy upload HTML → gateway CUSTOM_REPORT_UPSERT (DB-Writer). */
export async function POST(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.json({ detail: 'Gateway o admin API key no configurados' }, { status: 503 });
  }

  const reportId = encodeURIComponent(ctx.params.reportId || '');
  const target = `${base}/api/v1/admin/reports/${reportId}/upload`;

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json({ detail: 'multipart/form-data requerido' }, { status: 400 });
  }

  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  if (auth.actor) headers['X-Duckclaw-Actor'] = auth.actor;

  try {
    const res = await fetch(target, { method: 'POST', headers, body: form, cache: 'no-store' });
    const text = await res.text();
    let data: unknown = text;
    try {
      data = JSON.parse(text);
    } catch {
      /* gateway devolvió texto plano */
    }
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error de red al gateway';
    return NextResponse.json({ detail: msg }, { status: 503 });
  }
}
