import { NextRequest, NextResponse } from 'next/server';
const isDev = process.env.NODE_ENV === 'development';

const FRAMED_HTML_CSP =
  "default-src 'self' https: data:; " +
  "script-src 'self' https: cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com cdn.tailwindcss.com 'unsafe-inline' 'wasm-unsafe-eval'; " +
  "style-src 'self' https: 'unsafe-inline'; " +
  "img-src 'self' https: data: blob:; " +
  "font-src 'self' https: data:; " +
  "media-src 'self' https: data: blob:; " +
  "worker-src 'self' blob:; " +
  "connect-src 'self' https: data: blob:; " +
  "frame-ancestors 'self'";

function isFramedHtmlRoute(pathname: string): boolean {
  return (
    /^\/api\/admin\/reports\/[^/]+$/.test(pathname) ||
    pathname === '/api/admin/duckdb/pgq-graph/html'
  );
}

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  if (isFramedHtmlRoute(pathname)) {
    const response = NextResponse.next();
    response.headers.set('Content-Security-Policy', FRAMED_HTML_CSP);
    response.headers.set('X-Frame-Options', 'SAMEORIGIN');
    return response;
  }

  // Next.js App Router injects inline bootstrap scripts; strict nonce-only CSP
  // blocks hydration (dead buttons, no fetch). Nonce wiring needs layout integration.
  const scriptSrc = isDev
    ? "script-src 'self' 'unsafe-eval' 'unsafe-inline' blob:"
    : "script-src 'self' 'unsafe-inline' blob:";

  const csp = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob: data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    // Pipecat WavMediaManager: audioWorklet.addModule(blob:...)
    "worker-src 'self' blob:",
    // The playground chat may be framed by our own pages (e.g. the chat bubble of a full-screen
    // HTML dashboard); everything else, and every other origin, stays unframeable.
    pathname.startsWith('/playground') ? "frame-ancestors 'self'" : "frame-ancestors 'none'",
  ].join('; ');

  const response = NextResponse.next();
  response.headers.set('Content-Security-Policy', csp);
  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
