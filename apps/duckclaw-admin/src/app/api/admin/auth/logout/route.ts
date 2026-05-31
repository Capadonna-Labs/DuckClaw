import { NextRequest } from 'next/server';
import { proxyAuthToGateway } from '@/lib/authProxy';

export async function POST(req: NextRequest) {
  return proxyAuthToGateway(req, 'logout', { method: 'POST' });
}
