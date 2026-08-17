import { NextRequest } from 'next/server';
import { invalidateBffSessionCache, proxyAuthToGateway } from '@/lib/authProxy';
import { updateDesktopAdminCredentials } from '@/lib/desktopEnvFile';

export async function POST(req: NextRequest) {
  invalidateBffSessionCache();
  const body = await req.text();
  const upstream = await proxyAuthToGateway(req, 'register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  if (!upstream.ok) return upstream;

  try {
    const submitted = JSON.parse(body) as { email?: unknown; password?: unknown };
    const email = typeof submitted.email === 'string' ? submitted.email : '';
    const password = typeof submitted.password === 'string' ? submitted.password : '';
    updateDesktopAdminCredentials(email, password);
  } catch {
    // The account was created by the gateway; failure to mirror desktop.env must not undo it.
  }
  return upstream;
}
