import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { listRunningPm2AppNames } from '@/lib/pm2RunningApps';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const running = listRunningPm2AppNames();
  const offline = PM2_LOGGABLE_APPS.filter((name) => !running.includes(name));

  return NextResponse.json({ running, offline, all: [...PM2_LOGGABLE_APPS] });
}
