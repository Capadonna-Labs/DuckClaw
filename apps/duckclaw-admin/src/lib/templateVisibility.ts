import type { TemplateSummary } from '@/types/admin';

/** Oculta scaffold interno (`default`) y workers marcados `internal_scaffold`. */
export function isVisibleTemplate(agent: TemplateSummary): boolean {
  if (agent.id === 'default') return false;
  if (agent.internal_scaffold === true) return false;
  return true;
}

export function filterVisibleTemplates(items: TemplateSummary[]): TemplateSummary[] {
  return items.filter(isVisibleTemplate);
}
