/** Cabeceras comunes al llamar al API Gateway desde el BFF (servidor Next). */
export function gatewayBase(): string | null {
  const raw =
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL?.trim() ||
    '';
  return raw ? raw.replace(/\/$/, '') : null;
}

export function adminApiKey(): string {
  return (process.env.DUCKCLAW_ADMIN_API_KEY || '').trim();
}

export function tailscaleAuthKey(): string {
  return (process.env.DUCKCLAW_TAILSCALE_AUTH_KEY || '').trim();
}

export function gatewayProxyHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...extra,
  };
  const admin = adminApiKey();
  if (admin) headers['X-Admin-Key'] = admin;
  const ts = tailscaleAuthKey();
  if (ts) headers['X-Tailscale-Auth-Key'] = ts;
  return headers;
}
