import { NextResponse } from 'next/server';
import { comfyuiStatusLocal } from '@/lib/comfyuiBff';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

// #region agent log
function dbg(hypothesisId: string, message: string, data: Record<string, unknown>) {
  fetch('http://127.0.0.1:7542/ingest/7eef0e1d-8424-45c4-8303-d7cb22712741', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'fd1dbb' },
    body: JSON.stringify({
      sessionId: 'fd1dbb',
      hypothesisId,
      location: 'comfyui/status/route.ts',
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
}
// #endregion

export const dynamic = 'force-dynamic';

/** Health ComfyUI: gateway primero; si 404 (gateway viejo), probe local. */
export async function GET() {
  const base = gatewayBase();
  const key = adminApiKey();

  if (base && key) {
    try {
      const res = await fetch(`${base}/api/v1/admin/comfyui/status`, {
        headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
        cache: 'no-store',
      });
      dbg('A', 'gateway comfyui/status', { status: res.status });
      if (res.status !== 404) {
        const text = await res.text();
        return new NextResponse(text, {
          status: res.status,
          headers: {
            'Content-Type': res.headers.get('content-type') || 'application/json',
            'X-Duckclaw-Comfyui-Via': 'gateway',
          },
        });
      }
    } catch (e) {
      dbg('B', 'gateway fetch failed', { err: String(e) });
    }
  }

  const local = await comfyuiStatusLocal();
  dbg('C', 'local comfyui status', { ok: local.ok, url: local.url });
  return NextResponse.json(local, {
    headers: { 'X-Duckclaw-Comfyui-Via': 'local-bff' },
  });
}
