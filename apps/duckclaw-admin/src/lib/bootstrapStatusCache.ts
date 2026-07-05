/** Cache server-side del probe bootstrap (evita pm2 jlist + 2× health en ráfaga). */

import type { AdminBootstrapStatus } from '@/lib/adminBootstrapStatus';

const TTL_MS = 8_000;

let cached: { status: AdminBootstrapStatus; expiresAt: number } | null = null;
let inflight: Promise<AdminBootstrapStatus> | null = null;

export async function resolveBootstrapStatusCached(
  loader: () => Promise<AdminBootstrapStatus>
): Promise<AdminBootstrapStatus> {
  const now = Date.now();
  if (cached && now < cached.expiresAt) {
    return cached.status;
  }
  if (inflight) {
    return inflight;
  }
  inflight = loader()
    .then((status) => {
      cached = { status, expiresAt: Date.now() + TTL_MS };
      return status;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Solo tests */
export function resetBootstrapStatusCacheForTests(): void {
  cached = null;
  inflight = null;
}
