import { NextRequest } from 'next/server';
import { invalidateBffSessionCache, proxyAuthToGateway } from '@/lib/authProxy';

export async function POST(req: NextRequest) {
  invalidateBffSessionCache();
  const body = await req.text();
  return proxyAuthToGateway(req, 'login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
}
