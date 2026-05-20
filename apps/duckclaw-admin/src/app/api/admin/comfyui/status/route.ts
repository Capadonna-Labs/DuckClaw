import { NextResponse } from 'next/server';
import { comfyuiStatusLocal } from '@/lib/comfyuiBff';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

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
    } catch {
      /* fallback local */
    }
  }

  const local = await comfyuiStatusLocal();
  return NextResponse.json(local, {
    headers: { 'X-Duckclaw-Comfyui-Via': 'local-bff' },
  });
}
