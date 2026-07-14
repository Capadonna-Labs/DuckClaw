import { NextRequest, NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';
import { adminPublicBase } from '@/lib/adminPublicBase';

export function mcpOAuthRedirectUri(req: NextRequest): string {
  const google = (process.env.GOOGLE_OAUTH_REDIRECT_URI || '').trim();
  if (google) return google.replace(/\/$/, '');
  const explicit = (process.env.DUCKCLAW_MCP_OAUTH_REDIRECT_URI || '').trim();
  if (explicit) return explicit.replace(/\/$/, '');
  return `${adminPublicBase(req)}/api/admin/mcp/connectors/oauth/callback`;
}

export async function handleMcpOAuthCallback(req: NextRequest): Promise<NextResponse> {
  const url = new URL(req.url);
  const code = (url.searchParams.get('code') || '').trim();
  const state = (url.searchParams.get('state') || '').trim();
  const error = (url.searchParams.get('error') || '').trim();
  const errorDescription = (url.searchParams.get('error_description') || '').trim();
  const publicBase = adminPublicBase(req);
  const failBase = `${publicBase}/mcp?tab=connectors&oauth=error`;
  const okBase = `${publicBase}/mcp?tab=connectors&oauth=success`;

  if (error) {
    const msg = encodeURIComponent((errorDescription || error).slice(0, 120));
    return NextResponse.redirect(`${failBase}&msg=${msg}`);
  }
  if (!code || !state) {
    return NextResponse.redirect(`${failBase}&msg=missing_code_or_state`);
  }

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.redirect(`${failBase}&msg=gateway_not_configured`);
  }

  try {
    const res = await fetch(`${base}/api/v1/admin/mcp/connectors/oauth/complete`, {
      method: 'POST',
      headers: {
        ...gatewayProxyHeaders({ 'X-Admin-Key': key, 'Content-Type': 'application/json' }),
      },
      body: JSON.stringify({ code, state, redirect_uri: mcpOAuthRedirectUri(req) }),
      cache: 'no-store',
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail =
        typeof data?.detail === 'string'
          ? data.detail
          : typeof data?.detail?.detail === 'string'
            ? data.detail.detail
            : `HTTP ${res.status}`;
      return NextResponse.redirect(`${failBase}&msg=${encodeURIComponent(detail.slice(0, 120))}`);
    }
    return NextResponse.redirect(okBase);
  } catch (err) {
    const msg = encodeURIComponent((err instanceof Error ? err.message : 'oauth_complete_failed').slice(0, 120));
    return NextResponse.redirect(`${failBase}&msg=${msg}`);
  }
}
