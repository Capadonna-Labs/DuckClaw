import { NextRequest } from 'next/server';
import { handleMcpOAuthCallback } from '@/lib/mcpOAuthCallback';

/** Google/Notion redirect URI registered without :8443 — served via Admin BFF on Tailscale 8443. */
export async function GET(req: NextRequest) {
  return handleMcpOAuthCallback(req);
}
