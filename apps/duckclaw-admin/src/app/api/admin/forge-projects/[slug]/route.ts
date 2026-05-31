import { NextRequest, NextResponse } from 'next/server';
import { deleteForgeProjectLocal } from '@/lib/forgeProjectsLocal';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Ctx = { params: { slug: string } };

async function proxy(slug: string, actor: string, init?: RequestInit) {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) return null;
  const target = `${base}/api/v1/admin/forge-projects/${encodeURIComponent(slug)}`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  headers['X-Duckclaw-Actor'] = actor;
  try {
    const res = await fetch(target, { ...init, headers, cache: 'no-store' });
    if (res.status === 404) return null;
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch {
    return null;
  }
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const slug = ctx.params.slug;
  const proxied = await proxy(slug, auth.actor, { method: 'DELETE' });
  if (proxied) return proxied;
  try {
    deleteForgeProjectLocal(slug);
    return NextResponse.json({ ok: true, id: slug, _via: 'local' });
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : 'Error' },
      { status: 404 }
    );
  }
}
