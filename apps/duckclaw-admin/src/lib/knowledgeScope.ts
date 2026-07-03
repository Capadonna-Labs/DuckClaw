export type KnowledgeScope = 'platform' | 'project' | 'both';

export const KNOWLEDGE_SCOPE_OPTIONS: {
  id: KnowledgeScope;
  label: string;
  hint: string;
  requiresProject?: boolean;
}[] = [
  {
    id: 'platform',
    label: 'Plataforma',
    hint: 'Conocimiento global del framework (sin proyecto).',
  },
  {
    id: 'project',
    label: 'Proyecto',
    hint: 'Solo documentos del proyecto elegido.',
    requiresProject: true,
  },
  {
    id: 'both',
    label: 'Ambos',
    hint: 'Plataforma + proyecto activo.',
    requiresProject: true,
  },
];

export function knowledgeScopeLabel(scope: string): string {
  return KNOWLEDGE_SCOPE_OPTIONS.find((o) => o.id === scope)?.label ?? scope;
}

export function defaultKnowledgeScope(projectId: string): KnowledgeScope {
  return projectId.trim() ? 'both' : 'platform';
}

export function normalizeKnowledgeScope(scope: string, projectId: string): KnowledgeScope {
  const raw = (scope || '').trim().toLowerCase();
  if (raw === 'platform' || raw === 'project' || raw === 'both') {
    if ((raw === 'project' || raw === 'both') && !projectId.trim()) return 'platform';
    return raw;
  }
  return defaultKnowledgeScope(projectId);
}
