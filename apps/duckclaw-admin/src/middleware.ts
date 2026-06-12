import { NextRequest, NextResponse } from 'next/server';
const isDev = process.env.NODE_ENV === 'development';

const REPORT_HTML_CSP =
  "default-src 'self' https: data:; " +
  "script-src 'self' https: cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com cdn.tailwindcss.com 'unsafe-inline'; " +
  "style-src 'self' https: 'unsafe-inline'; " +
  "img-src 'self' https: data: blob:; " +
  "font-src 'self' https: data:; " +
  "connect-src 'self' https:; " +
  "frame-ancestors 'self'";

function isReportHtmlRoute(pathname: string): boolean {
  return /^\/api\/admin\/reports\/[^/]+$/.test(pathname);
}

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  if (isReportHtmlRoute(pathname)) {
    const response = NextResponse.next();
    response.headers.set('Content-Security-Policy', REPORT_HTML_CSP);
    response.headers.set('X-Frame-Options', 'SAMEORIGIN');
    return response;
  }

  // Next.js App Router injects inline bootstrap scripts; strict nonce-only CSP
  // blocks hydration (dead buttons, no fetch). Nonce wiring needs layout integration.
  const scriptSrc = isDev
    ? "script-src 'self' 'unsafe-eval' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline'";

  const csp = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob: data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
  ].join('; ');

  const response = NextResponse.next();
  response.headers.set('Content-Security-Policy', csp);
  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
