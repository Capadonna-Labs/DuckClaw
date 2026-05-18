export type KanbanStatus = 'pendiente' | 'en_progreso' | 'completo';

export interface KanbanCard {
  id: string;
  title: string;
  description: string;
  status: KanbanStatus;
  worker_id?: string;
  /** Instancia swarm 1..n (base siempre 1). */
  swarm_slot?: number;
  /** Clave compuesta ``{worker_id}:{slot}`` para estados del gateway. */
  instance_key?: string;
  /** Ámbito chat Redis cuando el slot lo expone. */
  chat_scope?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export const KANBAN_COLUMNS: { id: KanbanStatus; title: string; hint: string }[] = [
  { id: 'pendiente', title: 'Pendiente', hint: 'Ideas y agentes por crear' },
  { id: 'en_progreso', title: 'En progreso', hint: 'Configuración en curso' },
  { id: 'completo', title: 'Completo', hint: 'Agente listo o resuelto' },
];

export const KANBAN_WORKER_FILTER_KEY = 'duckclaw-kanban-worker-filter';

export function kanbanInstanceKey(workerId: string, slot: number): string {
  return `${workerId}:${slot}`;
}

export function swarmCardTitle(workerId: string, slot: number): string {
  return `${workerId} ${slot}`;
}

export function isSwarmAutoSyncCard(card: KanbanCard): boolean {
  return card.tags.includes('auto-sync') && card.tags.includes('swarm');
}
