import { create } from 'zustand';
import { adminService } from '@/services/adminService';
import type { AdminHealth } from '@/types/admin';

const TTL_MS = 45_000;
let inflight: Promise<AdminHealth | null> | null = null;

type GatewayHealthState = {
  data: AdminHealth | null;
  error: boolean;
  fetchedAt: number;
  refresh: (force?: boolean) => Promise<AdminHealth | null>;
};

export const useGatewayHealthStore = create<GatewayHealthState>((set, get) => ({
  data: null,
  error: false,
  fetchedAt: 0,
  refresh: async (force = false) => {
    const { data, fetchedAt } = get();
    if (!force && data && Date.now() - fetchedAt < TTL_MS) {
      return data;
    }
    if (inflight) return inflight;
    inflight = adminService
      .health()
      .then((health) => {
        set({ data: health, error: false, fetchedAt: Date.now() });
        return health;
      })
      .catch(() => {
        set({ error: true, fetchedAt: Date.now() });
        return null;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  },
}));
