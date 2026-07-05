import { create } from 'zustand';
import { adminService } from '@/services/adminService';
import type { AdminHealth } from '@/types/admin';

const TTL_MS = 45_000;
const STALE_GRACE_MS = 180_000;
const OFFLINE_AFTER_FAILURES = 3;

let inflight: Promise<AdminHealth | null> | null = null;
let consecutiveFailures = 0;

type GatewayHealthState = {
  data: AdminHealth | null;
  error: boolean;
  recovering: boolean;
  fetchedAt: number;
  refresh: (force?: boolean) => Promise<AdminHealth | null>;
  beginRecovery: () => void;
  endRecovery: () => void;
};

function staleDataStillUsable(data: AdminHealth | null, fetchedAt: number): boolean {
  return data != null && Date.now() - fetchedAt < STALE_GRACE_MS;
}

export const useGatewayHealthStore = create<GatewayHealthState>((set, get) => ({
  data: null,
  error: false,
  recovering: false,
  fetchedAt: 0,
  beginRecovery: () => {
    consecutiveFailures = 0;
    set({ recovering: true, error: false });
  },
  endRecovery: () => {
    set({ recovering: false });
  },
  refresh: async (force = false) => {
    const { data, fetchedAt, recovering } = get();
    if (!force && !recovering && data && Date.now() - fetchedAt < TTL_MS) {
      return data;
    }
    if (inflight) return inflight;

    inflight = adminService
      .health()
      .then((health) => {
        consecutiveFailures = 0;
        set({ data: health, error: false, recovering: false, fetchedAt: Date.now() });
        return health;
      })
      .catch(() => {
        consecutiveFailures += 1;
        const prev = get();
        const keepStale = staleDataStillUsable(prev.data, prev.fetchedAt);
        if (prev.recovering) {
          set({ data: prev.data, error: false, fetchedAt: Date.now() });
          return prev.data;
        }
        const offline = consecutiveFailures >= OFFLINE_AFTER_FAILURES && !keepStale;
        set({
          data: prev.data,
          error: offline,
          fetchedAt: Date.now(),
        });
        return keepStale ? prev.data : null;
      })
      .finally(() => {
        inflight = null;
      });

    return inflight;
  },
}));
