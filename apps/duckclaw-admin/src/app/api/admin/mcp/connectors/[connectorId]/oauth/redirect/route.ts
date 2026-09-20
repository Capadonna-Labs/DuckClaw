import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { adminPublicBase } from '@/lib/adminPublicBase';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

type Ctx = { params: { connectorId: string } };

function htmlEscape(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    if (char === '&') return '&amp;';
    if (char === '<') return '&lt;';
    if (char === '>') return '&gt;';
    if (char === '"') return '&quot;';
    return '&#39;';
  });
}

function oauthLaunchPage(authorizationUrl: string): NextResponse {
  const safeUrl = htmlEscape(authorizationUrl);
  return new NextResponse(
    `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conectar Notion</title>
  <style>
    :root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0b1117; color: #e8f0f6; }
    main { width: min(92vw, 560px); padding: 28px; border: 1px solid #263442; border-radius: 20px; background: #111a22; box-shadow: 0 20px 60px #0008; }
    h1 { margin: 0 0 12px; font-size: 28px; line-height: 1.1; }
    p { color: #a8b4bf; line-height: 1.45; }
    textarea { width: 100%; min-height: 120px; box-sizing: border-box; margin: 12px 0; padding: 12px; border-radius: 12px; border: 1px solid #314455; background: #071018; color: #cfe8ff; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
    a, button { border: 0; border-radius: 12px; padding: 12px 14px; font-weight: 800; text-decoration: none; cursor: pointer; }
    a.primary { background: #38bdf8; color: #061019; }
    button { background: #223140; color: #e8f0f6; }
    a.secondary { color: #9cc7ff; padding-left: 0; }
    small { display: block; margin-top: 16px; color: #7f8b96; }
  </style>
</head>
<body>
  <main>
    <h1>Conectar Notion</h1>
    <p>iOS puede abrir la app de Notion y perder el flujo OAuth. Si pasa, copia esta URL y pegala directamente en la barra de Safari.</p>
    <textarea id="url" readonly>${safeUrl}</textarea>
    <div class="actions">
      <a class="primary" href="${safeUrl}" rel="noopener">Abrir autorizacion</a>
      <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('url').value).then(()=>this.textContent='Copiado')">Copiar URL</button>
      <a class="secondary" href="/mcp?tab=connectors">Volver a MCP</a>
    </div>
    <small>Cuando Notion termine, debe volver a DuckClaw y mostrar OAuth success.</small>
  </main>
</body>
</html>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

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
    if (req.nextUrl.searchParams.get('auto') === '1') {
      return NextResponse.redirect(authorizationUrl);
    }
    return oauthLaunchPage(authorizationUrl);
  } catch (err) {
    const msg = encodeURIComponent(
      (err instanceof Error ? err.message : 'oauth_start_failed').slice(0, 120)
    );
    return NextResponse.redirect(`${adminPublicBase(req)}/mcp?tab=connectors&oauth=error&msg=${msg}`);
  }
}
