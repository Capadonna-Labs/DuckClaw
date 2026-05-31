/** Read CSRF double-submit cookie (client-only). */

export function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function mutationHeaders(method: string): HeadersInit {
  const m = (method || 'GET').toUpperCase();
  if (m === 'GET' || m === 'HEAD') return {};
  const csrf = getCsrfTokenFromCookie();
  return csrf ? { 'X-CSRF-Token': csrf } : {};
}
