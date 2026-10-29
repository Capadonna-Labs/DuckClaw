import type { World } from '@/lib/worldsTypes';

import { adminFetch } from './http';

type Body = Record<string, unknown>;
const send = (path: string, method: string, body?: Body) =>
  adminFetch<{ ok: boolean; world_id?: string; bot_id?: string; task_id?: string }>(path, {
    method,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });

export const worldsApi = {
  list: () => adminFetch<{ worlds: World[]; stale_after_s: number }>('/worlds'),
  createWorld: (body: Body) => send('/worlds', 'POST', body),
  updateWorld: (id: string, body: Body) => send('/worlds', 'PATCH', { id, ...body }),
  deleteWorld: (id: string) => send(`/worlds?id=${encodeURIComponent(id)}`, 'DELETE'),
  createBot: (worldId: string, body: Body) => send('/worlds/bots', 'POST', { world_id: worldId, ...body }),
  updateBot: (id: string, body: Body) => send('/worlds/bots', 'PATCH', { id, ...body }),
  deleteBot: (id: string) => send(`/worlds/bots?id=${encodeURIComponent(id)}`, 'DELETE'),
};
