import type { LucideIcon } from 'lucide-react';
import {
  Bot,
  BotMessageSquare,
  Brain,
  Cpu,
  Cog,
  Network,
  Sparkles,
  Workflow,
} from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';

export type AgentMetadata = {
  label: string;
  value: string;
};

const WORKER_ICONS: LucideIcon[] = [
  Bot,
  BotMessageSquare,
  Brain,
  Cpu,
  Cog,
  Network,
  Sparkles,
  Workflow,
];

function normalizeText(value: string | undefined): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
    .trim();
}

export function agentWorkerIcon(workerId: string): LucideIcon {
  let hash = 0;
  for (const ch of workerId) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return WORKER_ICONS[hash % WORKER_ICONS.length] ?? Bot;
}

export function agentDescription(agent: TemplateSummary): string {
  return agent.description?.trim() ?? '';
}

/** Línea secundaria: descripción real o resumen factual de skills (sin copy de ayuda). */
export function agentCardSubtitle(agent: TemplateSummary): string {
  const description = agentDescription(agent);
  if (description) return description;

  const skills = (agent.skills_list ?? []).map((s) => s.trim()).filter(Boolean);
  if (skills.length === 0) return '';

  const preview = skills.slice(0, 3).join(', ');
  const extra = skills.length > 3 ? ` +${skills.length - 3}` : '';
  const noun = skills.length === 1 ? 'skill' : 'skills';
  return `${skills.length} ${noun}: ${preview}${extra}`;
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
