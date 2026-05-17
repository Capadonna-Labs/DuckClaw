export type KanbanStatus = 'pendiente' | 'en_progreso' | 'completo';

export interface KanbanCard {
  id: string;
  title: string;
  description: string;
  status: KanbanStatus;
  worker_id?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export const KANBAN_COLUMNS: { id: KanbanStatus; title: string; hint: string }[] = [
  { id: 'pendiente', title: 'Pendiente', hint: 'Ideas y agentes por crear' },
  { id: 'en_progreso', title: 'En progreso', hint: 'Configuración en curso' },
  { id: 'completo', title: 'Completo', hint: 'Agente listo o resuelto' },
];
