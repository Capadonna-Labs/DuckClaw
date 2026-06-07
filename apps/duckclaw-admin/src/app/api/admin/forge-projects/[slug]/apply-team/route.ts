import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Ctx = { params: { slug: string } };

export async function POST(req: NextRequest, ctx: Ctx) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;
  void ctx;
  return NextResponse.json(
    {
      detail: 'Aplicar equipo legacy fue retirado. Usa asignaciones en Proyectos DB-first.',
      code: 'legacy_forge_projects_retired',
    },
    { status: 410 }
  );
}
