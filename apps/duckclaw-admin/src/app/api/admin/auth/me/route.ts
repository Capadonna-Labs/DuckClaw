import { NextRequest } from 'next/server';
import { proxyAuthToGateway } from '@/lib/authProxy';

export const maxDuration = 60;

export async function GET(req: NextRequest) {
  return proxyAuthToGateway(req, 'me', { method: 'GET' });
}
