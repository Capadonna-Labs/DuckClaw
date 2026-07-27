import { NextRequest, NextResponse } from 'next/server';
import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import { isDesktopLiteMode, readDesktopEnvFile } from '@/lib/desktopEnvFile';
import { listRunningPm2AppNamesAsync } from '@/lib/pm2RunningApps';
import { PM2_LOGGABLE_APPS } from '@/lib/pm2LogApps';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function desktopLogsAppsResponse(mode: string) {
  const offline = PM2_LOGGABLE_APPS.filter((name) => name !== 'DuckClaw-Gateway');
  return NextResponse.json({
    running: ['DuckClaw-Gateway'],
    offline: [...offline],
    all: ['DuckClaw-Gateway'],
    mode,
  });
}

export async function GET(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin'] });
  if (!auth.ok) return auth.response;

  const lite = isDesktopLiteMode();
  const fileEnv = readDesktopEnvFile();

  if (lite) {
    return desktopLogsAppsResponse('desktop');
  }

  const running = await listRunningPm2AppNamesAsync();
  if (
    running.length === 0 &&
    process.platform === 'win32' &&
    fileEnv.DUCKCLAW_ADMIN_API_KEY?.trim()
  ) {
    return desktopLogsAppsResponse('desktop-fallback');
  }

  const offline = PM2_LOGGABLE_APPS.filter((name) => !running.includes(name));

  return NextResponse.json({ running, offline, all: [...PM2_LOGGABLE_APPS], mode: 'pm2' });
}
