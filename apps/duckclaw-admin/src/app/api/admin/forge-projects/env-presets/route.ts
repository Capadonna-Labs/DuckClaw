import { NextRequest, NextResponse } from 'next/server';
import { loadEnvForgePresets } from '@/lib/forgeProjectsLocal';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

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
