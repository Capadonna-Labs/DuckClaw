import type { KanbanCard, KanbanStatus } from '@/lib/kanbanTypes';
import {
  isSwarmAutoSyncCard,
  kanbanInstanceKey,
  swarmCardTitle,
} from '@/lib/kanbanTypes';
import { adminApiKey, gatewayBase, gatewayProxyHeaders } from '@/lib/gatewayProxy';

const AUTO_SYNC_TAG = 'auto-sync';
const SWARM_TAG = 'swarm';

interface SwarmInstance {
  worker_id: string;
  slot: number;
  chat_scope?: string | null;
}

function newCardId(): string {
  return `card_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export async function fetchKanbanTeamWorkers(): Promise<string[]> {
  return fetchPlaygroundWorkers();
}

async function fetchPlaygroundWorkers(): Promise<string[]> {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key) return [];
  const res = await fetch(`${base}/api/v1/admin/playground/config`, {
    headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
    cache: 'no-store',
  });
  if (!res.ok) return [];
  const data = (await res.json()) as { workers?: string[] };
  return Array.isArray(data.workers) ? data.workers.filter(Boolean) : [];
}

async function fetchSwarmSlots(workers: string[]): Promise<{
  instances: SwarmInstance[];
  states: Record<string, KanbanStatus>;
}> {
  const base = gatewayBase();
  const key = adminApiKey();
  if (!base || !key || workers.length === 0) {
    return { instances: [], states: {} };
  }
  const q = new URLSearchParams({ workers: workers.join(',') });
  const res = await fetch(`${base}/api/v1/admin/kanban/swarm-slots?${q}`, {
    headers: gatewayProxyHeaders({ 'X-Admin-Key': key }),
    cache: 'no-store',
  });
  if (!res.ok) return { instances: [], states: {} };
  const data = (await res.json()) as {
    instances?: SwarmInstance[];
    states?: Record<string, string>;
  };
  const valid: KanbanStatus[] = ['pendiente', 'en_progreso', 'completo'];
  const states: Record<string, KanbanStatus> = {};
  for (const [k, st] of Object.entries(data.states ?? {})) {
    if (valid.includes(st as KanbanStatus)) states[k] = st as KanbanStatus;
  }
  return {
    instances: Array.isArray(data.instances) ? data.instances : [],
    states,
  };
}

function migrateLegacyCard(card: KanbanCard, now: string): KanbanCard {
  if (!card.worker_id || card.swarm_slot != null) return card;
  if (!card.tags.includes(AUTO_SYNC_TAG)) return card;
  if (card.title !== card.worker_id) return card;
  return {
    ...card,
    title: swarmCardTitle(card.worker_id, 1),
    swarm_slot: 1,
    instance_key: kanbanInstanceKey(card.worker_id, 1),
    tags: [...new Set([...card.tags, SWARM_TAG])],
    updated_at: now,
  };
}

function upsertSwarmCard(
  cards: KanbanCard[],
  workerId: string,
  slot: number,
  status: KanbanStatus,
  chatScope: string | undefined,
  now: string,
): { cards: KanbanCard[]; changed: boolean } {
  const instanceKey = kanbanInstanceKey(workerId, slot);
  let changed = false;
  const next = [...cards];
  let idx = next.findIndex(
    (c) =>
      isSwarmAutoSyncCard(c) &&
      c.worker_id === workerId &&
      (c.swarm_slot === slot || c.instance_key === instanceKey),
  );
  if (idx < 0) {
    idx = next.findIndex(
      (c) =>
        c.tags.includes(AUTO_SYNC_TAG) &&
        c.worker_id === workerId &&
        slot === 1 &&
        (c.title === workerId || !c.swarm_slot),
    );
  }
  const desc =
    slot === 1
      ? 'Instancia base (sincronizado desde /workers)'
      : 'Ejecución paralela activa (swarm)';
  if (idx < 0) {
    next.unshift({
      id: newCardId(),
      title: swarmCardTitle(workerId, slot),
      description: desc,
      status,
      worker_id: workerId,
      swarm_slot: slot,
      instance_key: instanceKey,
      chat_scope: chatScope,
      tags: [AUTO_SYNC_TAG, SWARM_TAG],
      created_at: now,
      updated_at: now,
    });
    return { cards: next, changed: true };
  }
  const cur = next[idx];
  const patch: KanbanCard = {
    ...cur,
    title: swarmCardTitle(workerId, slot),
    description: desc,
    status,
    worker_id: workerId,
    swarm_slot: slot,
    instance_key: instanceKey,
    chat_scope: chatScope ?? cur.chat_scope,
    tags: [...new Set([...cur.tags, AUTO_SYNC_TAG, SWARM_TAG])],
    updated_at: now,
  };
  if (
    cur.title !== patch.title ||
    cur.status !== patch.status ||
    cur.swarm_slot !== patch.swarm_slot ||
    cur.instance_key !== patch.instance_key ||
    cur.chat_scope !== patch.chat_scope
  ) {
    next[idx] = patch;
    changed = true;
  }
  return { cards: next, changed };
}

/** Merge /workers team + swarm slots into local kanban cards. */
export async function syncKanbanCardsWithTeam(cards: KanbanCard[]): Promise<{
  cards: KanbanCard[];
  changed: boolean;
}> {
  const workers = await fetchPlaygroundWorkers();
  if (workers.length === 0) return { cards, changed: false };

  const { instances, states } = await fetchSwarmSlots(workers);
  const now = new Date().toISOString();
  let changed = false;
  let next = cards.map((c) => {
    const migrated = migrateLegacyCard(c, now);
    if (migrated !== c) changed = true;
    return migrated;
  });

  const activeKeys = new Set<string>();
  for (const inst of instances) {
    const slot = Number(inst.slot) || 0;
    if (!inst.worker_id || slot < 1) continue;
    activeKeys.add(kanbanInstanceKey(inst.worker_id, slot));
  }

  for (const workerId of workers) {
    const key1 = kanbanInstanceKey(workerId, 1);
    const status = states[key1] ?? states[workerId] ?? 'pendiente';
    const chat1 = instances.find((i) => i.worker_id === workerId && i.slot === 1)?.chat_scope;
    const r = upsertSwarmCard(
      next,
      workerId,
      1,
      status,
      chat1 != null ? String(chat1) : undefined,
      now,
    );
    next = r.cards;
    if (r.changed) changed = true;
  }

  for (const inst of instances) {
    const slot = Number(inst.slot) || 0;
    if (!inst.worker_id || slot < 2) continue;
    const key = kanbanInstanceKey(inst.worker_id, slot);
    const status = states[key] ?? 'en_progreso';
    const r = upsertSwarmCard(
      next,
      inst.worker_id,
      slot,
      status,
      inst.chat_scope != null ? String(inst.chat_scope) : undefined,
      now,
    );
    next = r.cards;
    if (r.changed) changed = true;
  }

  const beforeLen = next.length;
  next = next.filter((c) => {
    if (!isSwarmAutoSyncCard(c)) return true;
    const slot = c.swarm_slot ?? 1;
    if (slot < 2) return true;
    const key = c.instance_key ?? kanbanInstanceKey(c.worker_id ?? '', slot);
    return activeKeys.has(key);
  });
  if (next.length !== beforeLen) changed = true;

  return { cards: next, changed };
}
