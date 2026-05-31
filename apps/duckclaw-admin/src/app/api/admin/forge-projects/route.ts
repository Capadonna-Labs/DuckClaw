import { NextRequest, NextResponse } from 'next/server';
import {
  createForgeProjectLocal,
  listForgeProjectsLocal,
} from '@/lib/forgeProjectsLocal';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function proxyToGateway(
  req: NextRequest,
  subpath: string,
  actor: string,
  init?: RequestInit
) {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) return null;
  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/forge-projects${subpath}${url.search}`;
  const headers = gatewayProxyHeaders({ 'X-Admin-Key': key });
  headers['X-Duckclaw-Actor'] = actor;
  const ct = req.headers.get('content-type');
  if (ct) headers['Content-Type'] = ct;
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

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const proxied = await proxyToGateway(req, '', auth.actor);
  if (proxied) return proxied;
  return NextResponse.json({
    projects: listForgeProjectsLocal(),
    _via: 'local',
  });
}

export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const bodyText = await req.text();
  const proxied = await proxyToGateway(req, '', auth.actor, {
    method: 'POST',
    body: bodyText,
  });
  if (proxied) return proxied;

  let body: {
    id?: string;
    display_name?: string;
    members?: string[];
    coordinator?: string;
    shared_vault_id?: string;
    shared_context?: string;
  };
  try {
    body = JSON.parse(bodyText || '{}');
  } catch {
    return NextResponse.json({ detail: 'JSON inválido' }, { status: 400 });
  }

  try {
    const result = createForgeProjectLocal({
      id: (body.id || '').trim(),
      display_name: body.display_name,
      members: body.members ?? [],
      coordinator: body.coordinator,
      shared_vault_id: body.shared_vault_id,
      shared_context: body.shared_context,
    });
    return NextResponse.json({ ...result, _via: 'local' });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error';
    const status = msg.includes('ya existe') ? 409 : 400;
    return NextResponse.json({ detail: msg }, { status });
  }
}
