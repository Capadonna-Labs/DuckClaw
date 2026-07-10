import type { NextRequest } from 'next/server';

/** Public Admin base URL for OAuth redirects (never 0.0.0.0). */
export function adminPublicBase(req?: NextRequest): string {
  if (req) {
    const host = (req.headers.get('x-forwarded-host') || req.headers.get('host') || '')
      .split(',')[0]
      ?.trim();
    if (host && !host.startsWith('0.0.0.0')) {
      const proto =
        req.headers.get('x-forwarded-proto')?.split(',')[0]?.trim() ||
        (req.nextUrl.protocol === 'https:' ? 'https' : 'http');
      return `${proto}://${host}`.replace(/\/$/, '');
    }
  }

  const explicit = (process.env.DUCKCLAW_ADMIN_URL || process.env.NEXT_PUBLIC_DUCKCLAW_ADMIN_URL || '').trim();
  if (explicit) return explicit.replace(/\/$/, '');

  const fallback = (process.env.VERCEL_URL || '').trim();
  if (fallback) return `https://${fallback}`.replace(/\/$/, '');

  return 'http://127.0.0.1:3000';
}
