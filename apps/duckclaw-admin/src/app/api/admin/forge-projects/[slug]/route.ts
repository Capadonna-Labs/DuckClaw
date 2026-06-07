import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Ctx = { params: { slug: string } };

function gone() {
  return NextResponse.json(
    {
      detail: 'Forge Projects filesystem fue retirado. Usa Proyectos DB-first.',
      code: 'legacy_forge_projects_retired',
    },
    { status: 410 }
  );
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;
  void ctx;
  return gone();
}
