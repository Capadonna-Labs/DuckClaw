import { NextRequest } from 'next/server';
import { proxyAuthToGateway } from '@/lib/authProxy';

export async function GET(req: NextRequest) {
  return proxyAuthToGateway(req, 'me', { method: 'GET' });
}
