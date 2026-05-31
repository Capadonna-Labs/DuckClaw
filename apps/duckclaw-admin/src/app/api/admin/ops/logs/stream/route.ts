import { NextRequest } from 'next/server';
import { startPm2LogsStream } from '@/lib/pm2LogStream';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const apps = req.nextUrl.searchParams.get('apps');

  try {
    const ac = new AbortController();
    req.signal.addEventListener('abort', () => ac.abort(), { once: true });

    const { stream } = startPm2LogsStream(apps, ac.signal);

    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'X-Content-Type-Options': 'nosniff',
        'X-Duckclaw-Ops-Via': 'local-pm2-stream',
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Error al iniciar stream';
    return new Response(JSON.stringify({ detail: msg }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
