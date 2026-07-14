import { NextRequest } from 'next/server';
import { handleMcpOAuthCallback } from '@/lib/mcpOAuthCallback';

export async function GET(req: NextRequest) {
  return handleMcpOAuthCallback(req);
}
