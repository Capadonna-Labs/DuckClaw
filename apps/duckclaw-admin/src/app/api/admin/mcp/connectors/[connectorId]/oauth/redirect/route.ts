import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { adminPublicBase } from '@/lib/adminPublicBase';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

type Ctx = { params: { connectorId: string } };

export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req);
  if (!auth.ok) return auth.response;

  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) {
    return NextResponse.redirect(
      `${adminPublicBase(req)}/mcp?tab=connectors&oauth=error&msg=gateway_not_configured`
    );
  }

  const connectorId = encodeURIComponent(ctx.params.connectorId || '');
  const redirectUri = `${adminPublicBase(req)}/api/admin/mcp/connectors/oauth/callback`;
  try {
    const res = await fetch(
      `${base}/api/v1/admin/mcp/connectors/${connectorId}/oauth/start`,
      {
        method: 'POST',
        headers: gatewayProxyHeaders({
          'X-Admin-Key': key,
          'X-Duckclaw-Actor': auth.actor,
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({ redirect_uri: redirectUri }),
        cache: 'no-store',
      }
    );
    const data = await res.json().catch(() => ({}));
    const authorizationUrl = String(data?.authorization_url || '');
    if (!res.ok || !authorizationUrl) {
      const detail =
        typeof data?.detail === 'string'
          ? data.detail
          : typeof data?.detail?.detail === 'string'
            ? data.detail.detail
            : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    return NextResponse.redirect(authorizationUrl);
  } catch (err) {
    const msg = encodeURIComponent(
      (err instanceof Error ? err.message : 'oauth_start_failed').slice(0, 120)
    );
    return NextResponse.redirect(`${adminPublicBase(req)}/mcp?tab=connectors&oauth=error&msg=${msg}`);
  }
}
