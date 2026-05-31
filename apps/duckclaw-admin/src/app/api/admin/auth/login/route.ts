import { NextRequest } from 'next/server';
import { proxyAuthToGateway } from '@/lib/authProxy';

export async function POST(req: NextRequest) {
  const body = await req.text();
  return proxyAuthToGateway(req, 'login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
}
