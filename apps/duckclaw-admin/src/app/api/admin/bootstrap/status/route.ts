import { NextResponse } from 'next/server';
import { resolveAdminBootstrapStatus } from '@/lib/adminBootstrapStatus';
import { resolveBootstrapStatusCached } from '@/lib/bootstrapStatusCache';

export const dynamic = 'force-dynamic';

export async function GET() {
  const status = await resolveBootstrapStatusCached(resolveAdminBootstrapStatus);
  return NextResponse.json(status, {
    status: status.canAttemptLogin ? 200 : 503,
    headers: { 'Cache-Control': 'private, max-age=5' },
  });
}
