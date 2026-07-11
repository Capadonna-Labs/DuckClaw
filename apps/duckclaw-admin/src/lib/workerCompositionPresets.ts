import type { ToolProfile } from '@/lib/manifestQuickEdit';
import { DEFAULT_TOOL_PROFILE } from '@/lib/workerRoleTemplates';

/** Etiquetas legibles; perfiles legacy (minimal/rag_only) solo para workers antiguos. */
export const TOOL_PROFILE_LABELS: Record<ToolProfile, string> = {
  general: 'Asistente completo',
  rag_only: 'Enfocado en documentación (legacy)',
  minimal: 'Consultas ligeras (legacy)',
};

export { DEFAULT_TOOL_PROFILE };
