import { Agent, fetch as undiciFetch, type RequestInit as UndiciRequestInit } from 'undici';

/**
 * Undici corta el body a los 300s por defecto (UND_ERR_BODY_TIMEOUT).
 * SSE del playground y generación ComfyUI pueden superar ese tiempo sin cerrar el stream.
 */
const LONG_GATEWAY_DISPATCHER = new Agent({
  bodyTimeout: 0,
  headersTimeout: 120_000,
  connectTimeout: 30_000,
});

/** fetch al gateway sin límite de 300s en el cuerpo de respuesta (SSE / jobs largos). */
export function gatewayLongFetch(input: string | URL, init?: RequestInit): Promise<Response> {
  return undiciFetch(input, {
    ...(init as UndiciRequestInit),
    dispatcher: LONG_GATEWAY_DISPATCHER,
  }) as unknown as Promise<Response>;
}

/** Cabeceras comunes al llamar al API Gateway desde el BFF (servidor Next). */
export function gatewayBase(): string | null {
  const explicit =
    process.env.DUCKCLAW_GATEWAY_URL?.trim() ||
    process.env.NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL?.trim() ||
    '';
  if (explicit) return explicit.replace(/\/$/, '');
  const port = (process.env.DUCKCLAW_GATEWAY_PORT || '').trim();
  if (/^\d+$/.test(port)) {
    const host = (process.env.DUCKCLAW_GATEWAY_HOST || '127.0.0.1').trim() || '127.0.0.1';
    return `http://${host}:${port}`;
  }
  return null;
}

/** Texto de ayuda con la URL/puerto configurados en el BFF (sin hardcodear 8000). */
export function gatewayConnectHint(): string {
  const base = gatewayBase();
  if (base) return base;
  return 'DUCKCLAW_GATEWAY_URL o DUCKCLAW_GATEWAY_PORT en apps/duckclaw-admin/.env.local';
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
