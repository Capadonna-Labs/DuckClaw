import { NextRequest, NextResponse } from 'next/server';

import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { openExternalUrlOnHost } from '@/lib/openExternalHost';
import { isSafeExternalHttpUrl } from '@/lib/safeExternalHttpUrl';

/** Opens an http(s) URL in the host OS browser (desktop webview-friendly). */
export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  let body: { url?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: 'JSON inválido' }, { status: 400 });
  }

  const url = (body.url || '').trim();
  if (!isSafeExternalHttpUrl(url)) {
    return NextResponse.json(
      { detail: 'Solo se permiten URLs http(s) absolutas' },
      { status: 400 }
    );
  }

  try {
    await openExternalUrlOnHost(url);
    return NextResponse.json({ ok: true });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'No se pudo abrir el navegador';
    return NextResponse.json({ detail: msg }, { status: 500 });
  }
}
