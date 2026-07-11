/** Plantillas de rol para el wizard — todas usan tool_profile general (baseline completo). */

export type WorkerRoleTemplateId = 'general' | 'data_analyst' | 'support' | 'devops';

export type WorkerRoleTemplate = {
  id: WorkerRoleTemplateId;
  title: string;
  description: string;
  promptTemplate: string;
  suggestedSkills?: string[];
  webSearch?: boolean;
  browserSandbox?: boolean;
};

export const DEFAULT_TOOL_PROFILE = 'general' as const;

export const WORKER_ROLE_TEMPLATES: ReadonlyArray<WorkerRoleTemplate> = [
  {
    id: 'general',
    title: 'Asistente general',
    description: 'Conversación, datos, documentos e informes según el contexto del turno.',
    promptTemplate:
      'Agente de workspace que ayuda al usuario con lo que pida: conversación, consultas SQL read-only, búsqueda en documentos del vault, informes y scripts en sandbox cuando haga falta. Prioriza respuestas claras y pide aclaración si falta contexto.',
  },
  {
    id: 'data_analyst',
    title: 'Analista de datos',
    description: 'Explora esquemas, ejecuta SQL y resume hallazgos en lenguaje natural.',
    promptTemplate:
      'Analista de datos DuckClaw: inspecciona esquema, ejecuta SQL read-only, valida supuestos con el usuario y presenta tablas/resúmenes accionables. Usa sandbox solo para transformaciones que no caben en una query.',
    suggestedSkills: [],
  },
  {
    id: 'support',
    title: 'Soporte con documentación',
    description: 'Prioriza RAG y respuestas citando fuentes del vault.',
    promptTemplate:
      'Agente de soporte: busca primero en el conocimiento del proyecto (list/read/search), cita fuentes, y escala a SQL o web solo si el vault no alcanza. Tono empático y procedimental.',
    suggestedSkills: [],
    webSearch: true,
  },
  {
    id: 'devops',
    title: 'DevOps / operaciones',
    description: 'Diagnóstico operativo, logs, sandbox y web cuando hace falta.',
    promptTemplate:
      'Agente DevOps: revisa estado del stack, interpreta logs, propone pasos de mitigación y ejecuta scripts en sandbox bajo confirmación. Usa búsqueda web para errores desconocidos y documentación externa.',
    suggestedSkills: [],
    webSearch: true,
    browserSandbox: true,
  },
];

export function roleTemplateById(id: WorkerRoleTemplateId | null | undefined): WorkerRoleTemplate | undefined {
  if (!id) return undefined;
  return WORKER_ROLE_TEMPLATES.find((role) => role.id === id);
}

export function applyRoleTemplateToDraft<T extends {
  tool_profile: string;
  skills: string[];
  web_search: boolean;
  browser_sandbox: boolean;
}>(draft: T, roleId: WorkerRoleTemplateId | null): T {
  const role = roleTemplateById(roleId);
  const skills = new Set(draft.skills.map((s) => s.trim()).filter(Boolean));
  for (const skill of role?.suggestedSkills ?? []) {
    if (skill.trim()) skills.add(skill.trim());
  }
  return {
    ...draft,
    tool_profile: DEFAULT_TOOL_PROFILE,
    web_search: role?.webSearch ?? draft.web_search,
    browser_sandbox: role?.browserSandbox ?? draft.browser_sandbox,
    skills: Array.from(skills),
  };
}
