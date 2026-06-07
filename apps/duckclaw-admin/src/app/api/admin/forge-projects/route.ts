import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function gone() {
  return NextResponse.json(
    {
      detail: 'Forge Projects filesystem fue retirado de la consola. Usa Proyectos DB-first o Platform Orchestrator.',
      code: 'legacy_forge_projects_retired',
    },
    { status: 410 }
  );
}

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;
  return gone();
}

export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;
  return gone();
}
