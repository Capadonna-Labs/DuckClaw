import { NextRequest, NextResponse } from 'next/server';
import { loadEnvForgePresets } from '@/lib/forgeProjectsLocal';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  if ((req.headers.get('x-duckclaw-role') || 'admin') !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }
  const presets = loadEnvForgePresets().map((p) => ({
    id: p.id,
    display_name: p.display_name,
    coordinator: p.coordinator,
    members: p.members,
    shared_vault_id: p.shared_vault_id,
    shared_context: (p as { shared_context?: string }).shared_context,
  }));
  return NextResponse.json({ presets });
}
