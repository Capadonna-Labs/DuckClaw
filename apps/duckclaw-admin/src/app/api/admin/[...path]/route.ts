import { NextRequest, NextResponse } from 'next/server';

const WRITE_METHODS = new Set(['PUT', 'PATCH', 'POST', 'DELETE']);

function gatewayBase(): string | null {
  const raw =
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL?.trim() ||
    '';
  return raw ? raw.replace(/\/$/, '') : null;
}

function adminKey(): string {
  return (process.env.DUCKCLAW_ADMIN_API_KEY || '').trim();
}

async function proxy(req: NextRequest, segments: string[]) {
  const base = gatewayBase();
  const key = adminKey();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }
  if (!key) {
    return NextResponse.json({ detail: 'DUCKCLAW_ADMIN_API_KEY no configurada' }, { status: 503 });
  }

  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role === 'viewer' && WRITE_METHODS.has(req.method)) {
    return NextResponse.json({ detail: 'Solo lectura (rol viewer)' }, { status: 403 });
  }

  const sub = segments.join('/');
  const url = new URL(req.url);
  const target = `${base}/api/v1/admin/${sub}${url.search}`;

  const headers: Record<string, string> = {
    'X-Admin-Key': key,
    Accept: 'application/json',
  };
  const ct = req.headers.get('content-type');
  if (ct) headers['Content-Type'] = ct;

  const init: RequestInit = { method: req.method, headers, cache: 'no-store' };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.text();
  }

  const res = await fetch(target, init);
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path ?? []);
}
