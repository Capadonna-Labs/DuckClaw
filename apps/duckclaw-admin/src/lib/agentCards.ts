import type { TemplateSummary } from '@/types/admin';

export type AgentMetadata = {
  label: string;
  value: string;
};

function normalizeText(value: string | undefined): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
    .trim();
}

export function agentDescription(agent: TemplateSummary): string {
  return (
    agent.description?.trim() ||
    'Sin descripción pública. Añade `description` al manifest o un resumen en `soul.md`.'
  );
}

export function agentMetadata(agent: TemplateSummary): AgentMetadata[] {
  const metadata: AgentMetadata[] = [];
  const schema = agent.schema_name?.trim();
  const schemaLooksRepeated =
    schema &&
    (normalizeText(schema) === normalizeText(agent.id) ||
      normalizeText(schema) === normalizeText(agent.name));

  if (schema && !schemaLooksRepeated) {
    metadata.push({ label: 'Schema', value: schema });
  }
  if (agent.temperature != null) {
    metadata.push({ label: 'Temp', value: String(agent.temperature) });
  }

  return metadata;
}
