/** Plantillas mostradas al usuario sin jerga técnica (id interno → copy amigable). */
export interface TemplatePreset {
  id: string;
  title: string;
  subtitle: string;
  emoji: string;
  recommended?: boolean;
}

export const BEGINNER_TEMPLATE_PRESETS: TemplatePreset[] = [
  {
    id: 'default',
    title: 'Asistente personalizado',
    subtitle: 'Empiezas con un comportamiento base que tú defines en el siguiente paso.',
    emoji: '✨',
    recommended: true,
  },
  {
    id: 'industries/business_standard',
    title: 'Asistente de negocio',
    subtitle: 'Añade habilidades de datos y memoria empresarial.',
    emoji: '💼',
  },
  {
    id: 'support',
    title: 'Atención al cliente',
    subtitle: 'Responde dudas frecuentes y guía a tus usuarios con tono amable.',
    emoji: '🎧',
  },
  {
    id: 'research_worker',
    title: 'Investigación y resúmenes',
    subtitle: 'Busca información en la web y entrega informes claros.',
    emoji: '🔎',
  },
  {
    id: 'finanz',
    title: 'Finanzas personales',
    subtitle: 'Ayuda con presupuesto, gastos y conceptos financieros básicos.',
    emoji: '💰',
  },
];

/** Presets avanzados (ocultos por defecto en el wizard). */
export const ADVANCED_TEMPLATE_PRESETS: TemplatePreset[] = [
  {
    id: 'industries/business_standard',
    title: 'Business Standard',
    subtitle: 'Plantilla base del repositorio.',
    emoji: '⚙️',
  },
  {
    id: 'Quant-Trader',
    title: 'Trading cuantitativo',
    subtitle: 'Mercados, SQL financiero y prompts avanzados (usuarios expertos).',
    emoji: '📈',
  },
];

export function presetForTemplateId(templateId: string): TemplatePreset | undefined {
  return [...BEGINNER_TEMPLATE_PRESETS, ...ADVANCED_TEMPLATE_PRESETS].find((p) => p.id === templateId);
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
