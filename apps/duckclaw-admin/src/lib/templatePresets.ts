/** Plantillas mostradas al usuario (ids = worker_id del catálogo DB o seed). */

export interface TemplatePreset {
  id: string;
  title: string;
  subtitle: string;
  emoji: string;
  recommended?: boolean;
}

export function presetForTemplateId(
  templateId: string,
  presets: TemplatePreset[]
): TemplatePreset | undefined {
  return presets.find((p) => p.id === templateId);
}

export function slugFromAgentName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
}
