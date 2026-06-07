import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  return NextResponse.json(
    {
      detail: 'Presets DUCKCLAW_TEAM_* fueron retirados de Admin. Usa Proyectos DB-first.',
      code: 'legacy_forge_projects_retired',
    },
    { status: 410 }
  );
}
