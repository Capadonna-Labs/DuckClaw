import { NextResponse } from 'next/server';
import { resolveAdminBootstrapStatus, resetPm2BootstrapCache } from '@/lib/adminBootstrapStatus';
import { resolveBootstrapStatusCached, resetBootstrapStatusCacheForTests } from '@/lib/bootstrapStatusCache';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const nocache = new URL(req.url).searchParams.get('nocache') === '1';
  if (nocache) {
    resetBootstrapStatusCacheForTests();
    resetPm2BootstrapCache();
  }
  const status = await resolveBootstrapStatusCached(resolveAdminBootstrapStatus);
  return NextResponse.json(status, {
    status: status.canAttemptLogin ? 200 : 503,
    headers: { 'Cache-Control': 'private, max-age=5' },
  });
}
