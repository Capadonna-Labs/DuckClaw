import { NextResponse } from 'next/server';
import { adminApiKey } from '@/lib/gatewayProxy';
import { runStackRestartGatewayOnlyLocal } from '@/lib/stackRestartCore';
import { resetBootstrapStatusCacheForTests } from '@/lib/bootstrapStatusCache';
import { resetPm2BootstrapCache } from '@/lib/adminBootstrapStatus';

export const maxDuration = 300;
export const dynamic = 'force-dynamic';

/** Reinicio PM2 de emergencia en login (sin sesión) cuando bootstrap dice gateway caído. */
export async function POST() {
  if (!adminApiKey()) {
    return NextResponse.json(
      { ok: false, detail: 'Configura DUCKCLAW_ADMIN_API_KEY antes de reiniciar el stack.' },
      { status: 503 }
    );
  }

  try {
    const result = await runStackRestartGatewayOnlyLocal();
    resetBootstrapStatusCacheForTests();
    resetPm2BootstrapCache();
    return NextResponse.json(result, {
      status: result.ok ? 200 : 500,
      headers: { 'X-Duckclaw-Ops-Via': 'bootstrap-emergency' },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Error reiniciando stack';
    return NextResponse.json({ ok: false, detail: msg }, { status: 500 });
  }
}
