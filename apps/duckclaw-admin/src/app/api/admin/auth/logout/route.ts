import { NextRequest } from 'next/server';
import {
  BFF_SESSION_COOKIE,
  bffSessionKeyFromCookie,
  invalidateBffSessionCache,
} from '@/lib/bffSessionCache';
import { proxyAuthToGateway } from '@/lib/authProxy';

export async function POST(req: NextRequest) {
  const sessionKey = bffSessionKeyFromCookie(req.cookies.get(BFF_SESSION_COOKIE)?.value);
  invalidateBffSessionCache(sessionKey);
  return proxyAuthToGateway(req, 'logout', { method: 'POST' });
}
