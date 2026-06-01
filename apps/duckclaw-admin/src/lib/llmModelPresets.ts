/** Proveedores seleccionables desde la UI admin (alineado con gateway /model). */
export const SELECTABLE_LLM_PROVIDERS = new Set([
  'mlx',
  'ollama',
  'openai',
  'anthropic',
  'deepseek',
  'groq',
  'gemini',
  'openrouter',
]);

/** Slugs OpenRouter con etiqueta legible (id = valor enviado al gateway). */
export const OPENROUTER_MODEL_PRESETS: { id: string; label: string }[] = [
  { id: 'deepseek/deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
  { id: 'deepseek/deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
  { id: 'deepseek/deepseek-chat', label: 'DeepSeek Chat (legacy)' },
  { id: 'deepseek/deepseek-r1', label: 'DeepSeek R1' },
  { id: 'anthropic/claude-sonnet-4-5', label: 'Claude Sonnet 4.5' },
  { id: 'anthropic/claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
  { id: 'google/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { id: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
  { id: 'openai/gpt-4o-mini', label: 'GPT-4o mini' },
  { id: 'openai/gpt-4o', label: 'GPT-4o' },
  { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct' },
  { id: 'qwen/qwen3-235b-a22b', label: 'Qwen3 235B' },
];

const OPENROUTER_LABEL_BY_ID = Object.fromEntries(
  OPENROUTER_MODEL_PRESETS.map((p) => [p.id, p.label])
) as Record<string, string>;

/** Modelos sugeridos por proveedor (complementa model_example del catálogo). */
export const LLM_MODEL_PRESETS: Record<string, string[]> = {
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4o-mini', 'gpt-4o', 'o3-mini'],
  anthropic: ['claude-3-5-haiku-20241022', 'claude-sonnet-4-20250514'],
  groq: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'],
  gemini: ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'],
  openrouter: OPENROUTER_MODEL_PRESETS.map((p) => p.id),
  ollama: ['llama3.2', 'mistral', 'qwen2.5'],
  mlx: [],
};

export function isOpenRouterProvider(providerId: string): boolean {
  return (providerId || '').trim().toLowerCase() === 'openrouter';
}

export function modelLabelForOption(providerId: string, modelId: string): string {
  const pid = (providerId || '').trim().toLowerCase();
  const mid = (modelId || '').trim();
  if (!mid) return '—';
  if (pid === 'openrouter') {
    return OPENROUTER_LABEL_BY_ID[mid] ?? mid;
  }
  return mid;
}

export function modelOptionsForProvider(
  providerId: string,
  catalogModelExample?: string,
  currentModel?: string
): string[] {
  const pid = (providerId || '').trim().toLowerCase();
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (m: string) => {
    const v = (m || '').trim();
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push(v);
  };
  add((currentModel || '').trim());
  for (const m of LLM_MODEL_PRESETS[pid] ?? []) add(m);
  const example = (catalogModelExample || '').trim();
  if (example) add(example);
  return out;
}
