import { NextResponse } from 'next/server';
import { resolveAdminBootstrapStatus } from '@/lib/adminBootstrapStatus';

export const dynamic = 'force-dynamic';

export async function GET() {
  const status = await resolveAdminBootstrapStatus();
  return NextResponse.json(status, {
    status: status.canAttemptLogin ? 200 : 503,
    headers: { 'Cache-Control': 'no-store' },
  });
}
