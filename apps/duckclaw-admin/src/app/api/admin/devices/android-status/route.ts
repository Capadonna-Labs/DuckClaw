import { NextResponse } from 'next/server';
import { androidDeviceStatusLocal } from '@/lib/androidAdbBff';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

export const dynamic = 'force-dynamic';

/** Telemetría física Android: gateway primero; fallback probe local ADB+MCP. */
export async function GET() {
  const base = gatewayBase();
  const key = adminApiKey();

  if (base && key) {
    try {
      const res = await fetch(`${base}/api/v1/admin/devices/android-status`, {
        headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
        cache: 'no-store',
      });
      if (res.status !== 404) {
        const text = await res.text();
        return new NextResponse(text, {
          status: res.status,
          headers: {
            'Content-Type': res.headers.get('content-type') || 'application/json',
            'X-Duckclaw-Android-Via': 'gateway',
          },
        });
      }
    } catch {
      /* fallback local */
    }
  }

  const local = await androidDeviceStatusLocal();
  return NextResponse.json(local, {
    headers: { 'X-Duckclaw-Android-Via': 'local-bff' },
  });
}
