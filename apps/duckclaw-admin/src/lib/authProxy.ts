/**
 * BFF auth proxy helpers — forward cookies; no duplicate validation.
 */

import { NextRequest, NextResponse } from 'next/server';
import { gatewayBase } from '@/lib/gatewayProxy';

export function gatewayAuthBase(): string {
  return (
    process.env.GATEWAY_INTERNAL_URL?.trim() ||
    gatewayBase() ||
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    ''
  ).replace(/\/$/, '');
}

export function forwardCookieHeader(req: NextRequest): string | undefined {
  return req.headers.get('cookie') ?? undefined;
}

export function applyUpstreamSetCookies(
  res: NextResponse,
  upstream: Response,
  opts?: { forceSecure?: boolean }
): void {
  const anyHeaders = upstream.headers as Headers & { getSetCookie?: () => string[] };
  const cookies =
    typeof anyHeaders.getSetCookie === 'function'
      ? anyHeaders.getSetCookie()
      : upstream.headers.get('set-cookie')
        ? [upstream.headers.get('set-cookie')!]
        : [];
  for (let c of cookies) {
    if (!c) continue;
    if (opts?.forceSecure && !/;\s*Secure/i.test(c)) {
      c = `${c}; Secure`;
    }
    res.headers.append('set-cookie', c);
  }
}

export async function proxyAuthToGateway(
  req: NextRequest,
  path: string,
  init?: RequestInit
): Promise<NextResponse> {
  const base = gatewayAuthBase();
  if (!base) {
    return NextResponse.json({ detail: 'DUCKCLAW_GATEWAY_URL no configurada' }, { status: 503 });
  }

  const cookie = forwardCookieHeader(req);
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (cookie) headers.cookie = cookie;

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/api/v1/admin/auth/${path}`, {
      ...init,
      headers,
      cache: 'no-store',
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'fetch failed';
    return NextResponse.json(
      {
        detail: `No se pudo contactar el gateway: ${detail}`,
        code: 'gateway_unreachable',
      },
      { status: 503 }
    );
  }

  const text = await upstream.text();
  const res = new NextResponse(text, {
    status: upstream.status,
    headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
  });
  const forceSecure =
    req.nextUrl.protocol === 'https:' ||
    req.headers.get('x-forwarded-proto')?.split(',')[0]?.trim() === 'https';
  applyUpstreamSetCookies(res, upstream, { forceSecure });
  return res;
}

export type SessionUser = {
  id: string;
  email: string;
  nombre: string;
  rol: string;
  initials?: string;
};

export async function resolveSessionUser(req: NextRequest): Promise<SessionUser | null> {
  const base = gatewayAuthBase();
  if (!base) return null;
  const cookie = forwardCookieHeader(req);
  if (!cookie) return null;

  try {
    const upstream = await fetch(`${base}/api/v1/admin/auth/me`, {
      headers: { cookie },
      cache: 'no-store',
    });
    if (!upstream.ok) return null;
    const data = (await upstream.json()) as { user?: SessionUser };
    return data.user ?? null;
  } catch {
    return null;
  }
}

export function validateCsrf(req: NextRequest): boolean {
  const header = (req.headers.get('x-csrf-token') || '').trim();
  const cookie = req.cookies.get('csrf_token')?.value?.trim();
  if (!header || !cookie) return false;
  return header === cookie;
}
