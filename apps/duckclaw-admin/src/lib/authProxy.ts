/**
 * BFF auth proxy helpers — forward cookies; no duplicate validation.
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  BFF_SESSION_COOKIE,
  bffSessionKeyFromCookie,
  coalesceBffSessionLookup,
  getCachedBffSession,
  invalidateBffSessionCache,
  setCachedBffSession,
} from '@/lib/bffSessionCache';
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

const AUTH_PROXY_TIMEOUT_MS = 8_000;

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
      signal: AbortSignal.timeout(AUTH_PROXY_TIMEOUT_MS),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'fetch failed';
    const timedOut =
      (err instanceof Error && err.name === 'TimeoutError') ||
      detail.toLowerCase().includes('aborted');
    return NextResponse.json(
      {
        detail: timedOut
          ? `Gateway no respondió en ${AUTH_PROXY_TIMEOUT_MS / 1000}s (${base})`
          : `No se pudo contactar el gateway: ${detail}`,
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
  const sessionKey = bffSessionKeyFromCookie(req.cookies.get(BFF_SESSION_COOKIE)?.value);
  if (!sessionKey) return null;

  const cached = getCachedBffSession(sessionKey);
  if (cached !== undefined) {
    return cached;
  }

  return coalesceBffSessionLookup(sessionKey, async () => {
    const cookie = forwardCookieHeader(req);
    if (!cookie) return null;

    try {
      const upstream = await fetch(`${base}/api/v1/admin/auth/me`, {
        headers: { cookie },
        cache: 'no-store',
        signal: AbortSignal.timeout(AUTH_PROXY_TIMEOUT_MS),
      });
      if (!upstream.ok) {
        invalidateBffSessionCache(sessionKey);
        return null;
      }
      const data = (await upstream.json()) as { user?: SessionUser };
      const user = data.user ?? null;
      if (user) {
        setCachedBffSession(sessionKey, user);
      } else {
        invalidateBffSessionCache(sessionKey);
      }
      return user;
    } catch {
      return null;
    }
  });
}

export { invalidateBffSessionCache };

export function validateCsrf(req: NextRequest): boolean {
  const header = (req.headers.get('x-csrf-token') || '').trim();
  const cookie = req.cookies.get('csrf_token')?.value?.trim();
  if (!header || !cookie) return false;
  return header === cookie;
}
