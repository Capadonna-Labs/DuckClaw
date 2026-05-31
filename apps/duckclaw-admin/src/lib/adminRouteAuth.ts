import { NextRequest, NextResponse } from 'next/server';
import { resolveSessionUser, validateCsrf, type SessionUser } from '@/lib/authProxy';
import { normalizeAdminRole } from '@/lib/roles';

type AllowedRole = 'admin' | 'user';

type AuthOk = {
  ok: true;
  user: SessionUser;
  role: AllowedRole;
  actor: string;
};

type AuthFail = {
  ok: false;
  response: NextResponse;
};

type AuthOptions = {
  roles?: AllowedRole[];
  requireCsrf?: boolean;
};

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export async function requireAdminRouteAuth(
  req: NextRequest,
  options: AuthOptions = {}
): Promise<AuthOk | AuthFail> {
  const shouldValidateCsrf = options.requireCsrf ?? WRITE_METHODS.has(req.method);
  if (shouldValidateCsrf && !validateCsrf(req)) {
    return {
      ok: false,
      response: NextResponse.json({ detail: 'CSRF token inválido o ausente' }, { status: 403 }),
    };
  }

  const user = await resolveSessionUser(req);
  if (!user) {
    return {
      ok: false,
      response: NextResponse.json({ detail: 'No autenticado' }, { status: 401 }),
    };
  }

  const role = normalizeAdminRole(user.rol) as AllowedRole;
  const allowed = options.roles ?? ['admin', 'user'];
  if (!allowed.includes(role)) {
    return {
      ok: false,
      response: NextResponse.json({ detail: 'Operación reservada para admin' }, { status: 403 }),
    };
  }

  return {
    ok: true,
    user,
    role,
    actor: user.email,
  };
}
