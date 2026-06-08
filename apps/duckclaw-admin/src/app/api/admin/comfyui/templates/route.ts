import { NextResponse } from 'next/server';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

export const dynamic = 'force-dynamic';

function gatewayStale() {
  return NextResponse.json(
    {
      detail: 'Catálogo ComfyUI DB-first requiere endpoint Gateway /api/v1/admin/comfyui/templates.',
      code: 'gateway_stale',
    },
    { status: 503 }
  );
}

/** Lista workflows solo desde gateway/DB-first. No lee workflows desde filesystem. */
export async function GET() {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) return gatewayStale();

  try {
    const res = await fetch(`${base}/api/v1/admin/comfyui/templates`, {
      headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
      cache: 'no-store',
    });
    if (res.status === 404) return gatewayStale();
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('content-type') || 'application/json',
        'X-Duckclaw-Comfyui-Via': 'gateway',
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail: 'No se pudo contactar el Gateway para catálogo ComfyUI DB-first.',
        code: 'gateway_unreachable',
      },
      { status: 503 }
    );
  }
}
