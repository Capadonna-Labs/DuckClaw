import { NextResponse } from 'next/server';
import { listComfyuiTemplatesLocal } from '@/lib/comfyuiBff';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

export const dynamic = 'force-dynamic';

/** Lista workflows: gateway primero; si 404, lee disco local. */
export async function GET() {
  const base = gatewayBase();
  const key = adminApiKey();

  if (base && key) {
    try {
      const res = await fetch(`${base}/api/v1/admin/comfyui/templates`, {
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
      /* gateway caído → local */
    }
  }

  return NextResponse.json(listComfyuiTemplatesLocal(), {
    headers: { 'X-Duckclaw-Comfyui-Via': 'local-bff' },
  });
}
